# Q4 结果报告

正式第四问结果采用附录4物性和附件2实测半径收缩，临界时间为 **51.0920106837 h**，临界时表面半径为 **1.2000 cm**。根后 1 s 的全域最大含水率严格低于 0.15 kg/kg。

| 案例 | 临界时间 / h | 临界半径 / cm | 中心C | 表面C |
| --- | ---: | ---: | ---: | ---: |
| A_appendix3_fixed_N5120 | 57.4748038075 | 2.0000 | 0.150000 | 0.052647 |
| B_appendix3_shrink_N5120 | 25.2440798099 | 1.2030 | 0.150000 | 0.054411 |
| C_appendix4_fixed_N5120 | >72 |  |  |  |
| D_appendix4_shrink_N5120 | 51.0921207851 | 1.2000 | 0.150000 | 0.052608 |
| main_appendix4_shrink_N20480 | 51.0920106837 | 1.2000 | 0.150000 | 0.052608 |

表6见 `results/q4/table6.csv` 与 `results/q4/table6.md`，Excel交付表为 `results/result4.xlsx`，独立回读证据见 `results/q4/export_verification.json`。固定物理半径超过当前药材表面的单元格留空，末列始终为动态药材表面。

图源与论文图位于 `results/q4/figure_data/` 和 `figures/q4/`。A/B/C/D 对照用于分离物性与几何影响；正式高精度行使用 `main_appendix4_shrink_N20480`，不把 5120 网格对照当作最终答案。
