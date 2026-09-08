# -*- coding: utf-8 -*-
"""注册表维护工具（registry_maintenance.py）。

修复运行时发现流程历史上造成的三类退化（默认预演，--apply 才写回）：
1. 基线记录元数据被目录数据覆盖（机构名加英文后缀、多模态/发布月/价格被改）->
   用代码内基线（DEFAULT_MODELS）回填人工维护字段；核验记录与发现渠道保留不动。
2. 同一模型被异写重复录入（GLM 5.3 vs GLM-5.3、Qwen3.8 Max (0902) vs Qwen 3.8 Max、
   DeepSeek V4 Flash 0731 vs DeepSeek V4 Flash）-> 按 canonical_model_key 归并，
   基线记录优先保留，重复记录仅在基线缺字段/缺后备值时做填补。
3. 发现记录的属性列被写成"多模态/商用/免费"这类与专列重复的标签 -> 重新按名称
   推导定位描述（旗舰/轻量/预览/翻译），与基线属性列同一内容形式；同时把可判定
   机构的 OpenRouter provider slug 规范化为机构显示名并修正 region。

用法：
  python registry_maintenance.py            # 预演（dry-run），只打印将发生的变更
  python registry_maintenance.py --apply    # 实际写回（先自动备份到 .zcode/backups/）
"""
import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from export_benchmark_excel import (  # noqa: E402
    DEFAULT_MODELS,
    DEFAULT_REGISTRY_PATH,
    canonical_model_key,
    load_or_init_registry,
)
from model_taxonomy import classify_institution, institution_display  # noqa: E402
from discover_models import derive_attribute  # noqa: E402

BASELINE_FIELDS = (
    "institution", "attribute", "multimodal", "release_date",
    "price_input", "price_output", "notes", "source_url", "footnote_tag",
    "gpqa_tag", "gpqa_url", "swe_tag", "swe_url", "mmlu_tag", "mmlu_url",
    "gpqa", "swe_verified", "swe_pro", "mmlu_pro",
)


def backup_registry(registry_path):
    root = os.path.dirname(os.path.dirname(SCRIPT_DIR))
    backup_dir = os.path.join(root, ".zcode", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"models_registry.pre-maint-{ts}.json")
    with open(registry_path, "r", encoding="utf-8") as src, open(dest, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    return dest


def heal_baseline(models):
    """用 DEFAULT_MODELS 回填同名基线记录的人工字段；返回修复条数。"""
    baseline = {m["name"].strip().lower(): m for m in DEFAULT_MODELS}
    healed = 0
    for m in models:
        ref = baseline.get(m["name"].strip().lower())
        if not ref:
            continue
        changed = False
        for k in BASELINE_FIELDS:
            if k in ref and m.get(k) != ref[k]:
                m[k] = ref[k]
                changed = True
        healed += 1 if changed else 0
    return healed


def dedupe(models):
    """按 canonical_model_key 归并同实体记录；返回 (models, 归并报告列表)。"""
    groups = {}
    for m in models:
        ck = canonical_model_key(m["name"])
        if not ck:
            continue
        groups.setdefault(ck, []).append(m)

    keep_of = {}
    report = []
    for ck, members in groups.items():
        if len(members) == 1:
            continue
        # 保留者：人工基线优先 -> 声称值多者优先 -> 列表靠前者
        members_sorted = sorted(
            members,
            key=lambda m: (bool(m.get("discovered_via")),
                           -sum(1 for k in ("gpqa", "swe_verified", "mmlu_pro") if m.get(k) is not None)),
        )
        keeper = members_sorted[0]
        dups = members_sorted[1:]
        keep_of[id(keeper)] = dups
        for dup in dups:
            for k, v in dup.items():
                if k in ("name", "verification", "discovered_via") or v is None:
                    continue
                if keeper.get(k) is None:
                    keeper[k] = v
            # 核验记录：缺失整条则搬入；已有条目但非 ok 且无后备值时补后备值
            if not isinstance(keeper.get("verification"), dict):
                keeper["verification"] = {}
            keeper_vm = keeper["verification"].setdefault("metrics", {})
            for key, entry in ((dup.get("verification") or {}).get("metrics") or {}).items():
                cur = keeper_vm.get(key)
                if cur is None:
                    keeper_vm[key] = entry
                elif cur.get("status") != "ok" and not cur.get("fallback") and entry.get("fallback"):
                    cur["fallback"] = entry["fallback"]
        report.append({"keeper": keeper["name"], "removed": [d["name"] for d in dups]})
    return [m for m in models if not any(m in ds for ds in keep_of.values())], report


def refresh_discovered(models):
    """发现记录：属性重生成 + 机构/region 规范化；返回 (models, 变更报告)。

    名称命中基线的记录一律跳过（即使历史上被合并过 discovered_via），
    其属性/机构以基线人工值为准。
    """
    baseline_names = {m["name"].strip().lower() for m in DEFAULT_MODELS}
    changed = []
    for m in models:
        if not m.get("discovered_via"):
            continue
        if m["name"].strip().lower() in baseline_names:
            continue
        note = {}
        new_attr = derive_attribute(m["name"])
        if new_attr != m.get("attribute"):
            note["attribute"] = f"{m.get('attribute')!r} -> {new_attr!r}"
            m["attribute"] = new_attr
        region, key = classify_institution(m.get("institution"))
        if key:
            display = institution_display(key, fallback=m.get("institution") or "")
            if display and display != m.get("institution"):
                note["institution"] = f"{m.get('institution')!r} -> {display!r}"
                m["institution"] = display
            if region != "unknown" and m.get("region") != region:
                note["region"] = f"{m.get('region')!r} -> {region!r}"
                m["region"] = region
        if note:
            changed.append({"model": m["name"], **note})
    return models, changed


def main():
    ap = argparse.ArgumentParser(description="注册表维护：基线回填/同实体归并/属性重生成")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY_PATH)
    ap.add_argument("--apply", action="store_true", help="实际写回（默认仅预演）")
    args = ap.parse_args()

    models = load_or_init_registry(args.registry)
    before = len(models)

    healed = heal_baseline(models)
    models, merge_report = dedupe(models)
    models, attr_report = refresh_discovered(models)

    print(f"记录数: {before} -> {len(models)}")
    print(f"基线回填: {healed} 条")
    print(f"同实体归并: {len(merge_report)} 组")
    for r in merge_report:
        print(f"  保留 {r['keeper']}  <- 移除 {r['removed']}")
    print(f"发现记录规范化: {len(attr_report)} 条")
    for r in attr_report:
        print(f"  {r['model']}: " + "; ".join(f"{k} {v}" for k, v in r.items() if k != "model"))

    if args.apply:
        dest = backup_registry(args.registry)
        with open(args.registry, "w", encoding="utf-8") as f:
            json.dump(models, f, ensure_ascii=False, indent=2)
        print(f"已写回 {args.registry}（备份: {dest}）")
    else:
        print("预演完成（未写回；加 --apply 生效）")


if __name__ == "__main__":
    main()
