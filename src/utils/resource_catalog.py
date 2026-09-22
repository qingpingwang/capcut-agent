"""资源目录适配层；查询与应用效果共享项目现有加载器，不在 Skill 中复制目录。

当前协议子模块只接受材质配置，没有资源目录 API。若上游新增目录服务，
替换 load_catalog 即可，Agent 和 Skill 的查询契约无需改变。
"""
from rag import get_jianying_res_info


def load_catalog():
    return get_jianying_res_info()


def list_categories():
    catalog = load_catalog()
    return {"source": "rag/data", "categories": [
        {"name": name, "count": len(items)} for name, items in sorted(catalog.items())
    ]}


def search_resources(category=None, keyword="", offset=0, limit=20):
    if offset < 0 or not 1 <= limit <= 100:
        return {"error": "offset 必须非负，limit 必须在 1 到 100 之间"}
    catalog = load_catalog()
    if category and category not in catalog:
        return {"error": f"资源分类不存在: {category}", "categories": sorted(catalog)}
    keyword = keyword.casefold()
    matches = [
        {"category": kind, "name": name, "desc": info.get("desc", "")}
        for kind, items in sorted(catalog.items()) if not category or kind == category
        for name, info in sorted(items.items())
        if keyword in f"{name} {info.get('desc', '')}".casefold()
    ]
    page = matches[offset:offset + limit]
    return {"source": "rag/data", "items": page, "total": len(matches),
            "offset": offset, "limit": limit,
            "next_offset": offset + len(page) if offset + len(page) < len(matches) else None}


def get_resource(category, name):
    catalog = load_catalog()
    try:
        return catalog[category][name]
    except KeyError:
        raise ValueError(f"资源不存在或已被移除: {category}/{name}，请重新查询资源目录") from None
