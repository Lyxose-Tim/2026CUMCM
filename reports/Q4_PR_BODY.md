# feat: 完成第四问收缩域建模与结果

## 变更摘要

本 PR 在已审核的 Q3 固定半径事件求解基础上，新增第四问收缩域求解链路：

- 新增 `q4/` 模块和 `configs/q4.json`，读取附件2半径历史、附件1环境、result4模板与输入哈希。
- 使用材料坐标 `xi=r/R(t)`，实现附录4变物性热湿耦合、动态表面 Robin 边界和全域最大含水率事件定位。
- 交付表6、`results/result4.xlsx`、Q4结果报告、验证报告、论文图和图源数据。
- 保留 A/B/C/D 四组对照：附录3/4 × 固定/收缩半径，用于解释几何收缩和物性变化的作用。

## 模型闭合

第四问假设长度不变、径向材料点仿射收缩，干基含水率不因几何收缩额外浓缩。材料坐标方程为：

```text
U_t = R(t)^(-2) * 1/xi * d/dxi [xi D4(U,Theta) U_xi]
rho4(U) cp4(U) Theta_t = R(t)^(-2) * 1/xi * d/dxi [xi k4(U) Theta_xi]
```

表面边界为 `-D4/R * U_xi = hm(U_s-Ce)` 和 `-k4/R * Theta_xi = h(Theta_s-Te)`。附件2半径采用分段线性插值，4 h 后环境延拓继续沿用第二、三问的最后一小时均值规则。

## 关键结果

正式案例：`main_appendix4_shrink_N20480`。

- 第四问临界时间：`51.0920106837 h`
- 临界表面半径：`1.2000 cm`
- 10240 到 20480 网格临界时间差：`0.0755348963 s`
- Excel：`results/result4.xlsx`
- 表6：`results/q4/table6.csv` 与 `results/q4/table6.md`

对照结果：

| 案例 | 临界时间 / h | 说明 |
| --- | ---: | --- |
| A_appendix3_fixed_N5120 | 57.4748038075 | 退化到 Q3 同网格 |
| B_appendix3_shrink_N5120 | 25.2440798099 | 仅引入收缩 |
| C_appendix4_fixed_N5120 | >72 | 仅换附录4物性，72 h 内未全域达标 |
| D_appendix4_shrink_N5120 | 51.0921207851 | 附录4物性 + 收缩 |

## 验证

- `python -m pytest -q --basetemp <ascii-temp> -p no:cacheprovider`：`94 passed in 6.78s`
- `q4.validation`：通过全域严格越阈、正含水率、温度历史包络、半径单调、域外空白掩码、水分平衡和事件斜率检查。
- Q3固定域退化回归：C最大差 `3.284445493e-09`，T最大差 `6.188763280e-09`。
- `q4.check_export`：`result4.xlsx` 回读通过，3066 行、23 列、44287 个数值单元、23165 个域外空白，最大数值差 `0.0`。

## 复现命令

```bash
python -m q4.run --data-root <A题目录> --workers 3
python -m q4.run --data-root <A题目录> --cases main_appendix4_shrink_N10240 main_appendix4_shrink_N20480 --workers 2
python -m q4.validation
python -m q4.export --data-root <A题目录>
node scripts/build_result4.mjs
python -m q4.check_export
python -m q4.figures
python -m q4.reports
```

或使用：

```bash
python -m q4.reproduce --data-root <A题目录> --workers 3
```

## 尚未覆盖

- 本 PR 不写整篇论文正文，不声称实物实验精度。
- 4 h 后环境仍依赖第二、三问采用的长期延拓假设。
- C 组对照 72 h 未达标作为结构诊断保留，不作为第四问正式终点。
