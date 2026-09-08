# -*- coding: utf-8 -*-
"""技能级配置读取（skill_config.py）。

配置文件与脚本同目录：skill/config.json（随技能一起安装/分发）：

    {
      "cache": {
        "enabled": true   # 默认开启本地永久存储：报告优先取自本地，避免重复联网查询
      }
    }

语义（永久存储，不是会过期的临时缓存）：
- 每次运行联网获取一次 OpenRouter 目录（一次调用），与本地永久存储对比去重：
  本地已有的模型不再获取任何数据，只有本地没有的新模型才入库、整理、取评分；
- 模型信息与评分（含来源 URL）一旦存入注册表就永久复用，报告生成不重复查询；
- 关闭方式：把 enabled 改为 false（本次起忽略本地存储，全部候选视为新增并重新取
  评分）；单次忽略：discover_models.py --no-cache；单次强制重验评分：verify_scores.py --fresh。
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "cache": {
        "enabled": True,
    }
}


def load_config(path=CONFIG_PATH):
    """读取配置；文件缺失/损坏时回退默认值。返回深拷贝后的 dict。"""
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
    except Exception:
        return cfg
    for section, vals in user.items():
        if isinstance(vals, dict) and isinstance(cfg.get(section), dict):
            cfg[section].update(vals)
        else:
            cfg[section] = vals
    return cfg


def cache_enabled(cfg=None):
    cfg = cfg or load_config()
    return bool(cfg.get("cache", {}).get("enabled", True))