# 转场与效果

1. 先调用 list_jianying_resource_categories 查询分类，再调用 search_jianying_resources 按关键词分页检索。只有真实返回的分类、名称可用于后续工具，不虚构资源 ID。完整渲染配置由添加效果的工具在内部加载，查询不返回 JSON。资源分析可委派 resource-analyst。
2. 转场仅适用于同轨相邻片段，只给前一片段添加转场资源，不给两段重复添加。
3. 文字动画、画面动画附加到已有片段，使用 add_material_to_segment，不创建独立轨道。
4. 全局特效、滤镜、音效分别使用 effect、filter、audio 类型轨道，优先复用已有轨道。
5. 使用 add_effect_to_track、add_filter_to_track、add_audio_effect_to_track 时，category 和 name 必须匹配目录。
6. 效果起点和持续时间以毫秒计算，核对覆盖的时间范围。
7. 调色、缩放、平移等参数参考工具 schema；不要根据名称猜测参数单位。
8. 添加完成后检查工程和轨道数据，记录效果实际关联的片段或轨道。
