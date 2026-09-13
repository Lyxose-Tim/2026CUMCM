# 技术路线图交付报告

## 交付

- 可编辑源：figures/paper/fig01_model_roadmap.drawio
- 论文 PDF：figures/paper/fig01_model_roadmap.pdf
- 节点数据：results/paper_figure_data/fig01_model_roadmap_nodes.csv
- 连线数据：results/paper_figure_data/fig01_model_roadmap_edges.csv
- 圆柱坐标与表面通量语义：results/paper_figure_data/fig01_model_geometry.csv
- 总清单：results/paper_figure_manifest.json

图示表达题面输入、Q1–Q4 递进、统一数值验证和表格/图源/报告交付，不承载任何未经计算的数值结论。

## 渲染路径

当前环境没有发现 drawio 或 draw.io 命令行程序，因此未伪造 DrawIO CLI 导出记录。仓库保留有效 mxGraph XML 源，同时由 paper_figures.py 根据同一节点和连线语义生成 PDF 后备版本。

后备 PDF 已用 Poppler 渲染为 PNG 做视觉核对。若目标机器安装 diagrams.net Desktop，可直接打开 drawio 源并重新导出；重新导出后必须刷新 results/paper_figure_manifest.json，不能沿用旧 PDF 摘要。

## 设计约束

- 四问沿水平方向递进，统一验证置于下方，避免箭头交叉。
- 输入、Q1/Q2、Q3、Q4、验证和交付使用不同但克制的语义色。
- 图中文字只说明变量关系和证据流，不在图内堆叠使用说明。
- CSV、DrawIO、PDF 和生成器均采用版本化摘要绑定。
