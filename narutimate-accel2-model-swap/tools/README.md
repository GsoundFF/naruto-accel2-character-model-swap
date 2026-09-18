# tools —— 通用化脚本模板

这四个脚本是把实例脚本里写死的路径与编号抽出来的通用版本。它们**不含任何游戏数据**，
你只需要提供自己的游戏目录与镜像。

## 前置

```powershell
# 1) 游戏目录（含 _extract/data_inner.iso 与 _extract/inner_filelist.txt）
$env:ROOM = "D:\path\to\game\ROOM"
# 2) 开源 CCS 解析库 blender_ccs_importer 的上级目录（该目录下应有 ccs_lib\）
$env:CCS_LIB = "D:\path\to\blender_ccs_importer-main"
pip install numpy pillow          # 仅用于贴图渲染识别角色
```

`inner_filelist.txt` 每行 TAB 分隔：`路径;1 \t LBA \t gz长度`。
`gz长度` 既是文件在盘上的存储大小，也是**原位补丁的容量上限**。

## 工作流

```
1) analyze_pairs.py  <目标文件> <来源文件>
        ↓ 拿到：两个 trall clump 的骨骼与位置号、body 的 idx/mat/lookup、
                贴图 idx/clut、CLUT idx、空模型模板数量
2) swap_template.py  （把上面的数字填进 CONFIG，然后每种变体跑一次）
        ↓ 产出：_extract/replacement_surgical/<NAME>.CCS.gz（并做容量检查）
3) patch_inplace.py  （把 .gz 写回原版镜像的原始 extent）
        ↓ 产出：MOD 镜像
4) audit_iso.py      （逐扇区比对，确认只改了预期的几段）
```

三个变体（战斗 / MODEL / 1P）都要各跑一次第 1、2 步。
`1XXXBOD1`（1P 高模）是**选人画面 + 奥义演出**真正读取的文件，别漏。

## 各脚本要点

| 脚本 | 说明 |
|---|---|
| `ccs_common.py` | 公共库：读内层文件、解析/重建 CCS、名字映射（`name_pmap` / `occ_pmap`）、body 重定向、真实空模型模板、容量检查 |
| `analyze_pairs.py` | 结构 dump，用来填 CONFIG |
| `swap_template.py` | 换模模板；CONFIG 在文件顶部，含容量自检与块顺序校验 |
| `patch_inplace.py` | 原位补丁；会拒绝超容量的替换包，并在写入后回读校验 |
| `audit_iso.py` | 全盘比对；把非预期改动标成 `!! UNEXPECTED` |

## 最容易踩的两个坑

1. **左右同名骨骼**：1P 高模里左右骨名常完全相同（都叫 `clavicle`/`hand`…）。
   必须用 `occ_pmap()`（第 N 个对第 N 个），否则左右会绑到同一根骨上。
2. **容量**：替换包 gzip 后必须 ≤ 目标文件的存储大小。源模型比目标大时可能根本放不下，
   这时应该换方向或换来源，**不要硬塞**（会覆盖下一个文件、损坏镜像）。
