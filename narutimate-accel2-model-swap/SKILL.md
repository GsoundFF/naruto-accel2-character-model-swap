---
name: narutimate-accel2-model-swap
description: 究极觉醒2角色模型替换 —— 在 PS2《火影忍者疾风传 究极觉醒2》里把某个角色的外观换到另一个角色身上（保留动作/招式），战斗+奥义+选人三处模型一起换。用"外科手术式替换 CCS 模型块 + 原位补丁写回原 extent"的方法：跨骨架按名字映射、lookupList 槽位重映射、贴图/调色板移植、眼嘴刚性件处理、奥义 cut-in 机制、以及容量约束。Also usable for debugging such a mod that shows no effect, crashes on entering battle, or blackscreens.
whenToUse: 当用户要求"把 X 的模型换到 Y 上""换角色外观""换个皮肤""奥义也一起替换"，或需要排查这类 MOD 没生效/进战斗卡死/黑屏时使用。Use when swapping/replacing a character's model or appearance in Naruto Shippuuden Narutimate Accel 2 (PS2) or a similar CCS-based Narutimate title.
---

# PS2《火影忍者疾风传 究极觉醒2》角色外观替换（外科手术 + 原位补丁）

目标：让角色 **T（目标）** 在游戏里显示角色 **S（来源）** 的外观（身体+贴图+奥义+选人），
**但动作/招式/骨架仍是 T 的**。整文件替换会让游戏**进战斗卡死**（游戏按 T 的动画编号驱动 S 的骨架，
骨骼编号对不上就崩）。

> **方向先确认（最容易搞反）**："把 A 的模型换到 B 上" ⇒ **目标 = B，来源 = A**。
> 方向还决定容量能否满足（见第 7 节）。

核心方法两句话：
1. **外科手术**：只在 T 的文件里替换"外观相关块"（body 网格 / body 贴图 / 调色板 / 眼嘴小件），
   骨架、动画、名字表、Stream 全部保留 T 的。
2. **原位补丁**：不重建 CVM（加密卷，重建会黑屏），把新文件的 gzip 写回它在 ISO 里的**原 extent**。

本仓库 `tools/` 下有可直接复用的脚本模板：`analyze_pairs.py`（结构分析）、
`swap_template.py`（换模）、`patch_inplace.py`（原位补丁）、`audit_iso.py`（全盘校验）。

---

## 0. 环境与工具（先确认）

- 工作区（下称 ROOM）：游戏目录，含 `*.iso`、`_extract/`、脚本。
- `_extract/data_inner.iso` —— 从外层 `data.cvm` 里提取出来的**内层 ISO**（明文）。
- `_extract/inner_filelist.txt` —— TAB 分隔：`路径;1 \t LBA \t size`。
  `size` 就是该文件在盘上的 **gzip 长度**（= 原位补丁的容量上限）。
- CCS 解析库：开源项目 `blender_ccs_importer` 的 `ccs_lib`
  （`readCCS`、`ccsHeader`、`ccsIndex`、`CCSTypes`、`ccsDict`）。
- 替换包输出：`_extract/replacement_surgical/<NAME>.CCS.gz`。
- **外偏移公式**：`outer_offset = (CVM_LBA + 3 + innerLBA) * 2048`，
  本作 `CVM_LBA = 210454`、扇区 2048。（换盘/换游戏必须重新验证。）

**先验证映射再动手**：读原版 ISO 在 `outer_offset` 处 `size` 字节 → `gzip.decompress` →
前 16 字节应是 `01 00 cc cc 0d 00 00 00 CCSF2xxx…`。签名对不上说明公式/常量错。

## 1. 角色代码识别（禁止靠猜）

/PL/ 下同一角色常有多套代码（多为不同服装），尾字母常是颜色（W=白、R=红…）。

- 渲染 body 贴图（I8 + CLUT）成 PNG，**让用户肉眼确认**哪个代码是谁
  （当前模型可能无视觉能力，这一步必须由人确认）。
- 判据：`/PL/1XXXBOD1.CCS` 存在 ⇒ 有 1P 高模（可玩角色、有奥义）。
- 不要拿文件名字面猜（如 "KUR" 往往不存在）；
  更不要靠字符串搜索"角色选择表"（搜出来的多是二进制巧合，不是角色表）。

## 2. 文件角色分工（最重要的一张表）

| 路径 | 作用 | 备注 |
|---|---|---|
| `/PL/2XXXBOD1.CCS` | **战斗模型** | 进战斗看到的外观 |
| `/PL/1XXXBOD1.CCS` | **1P 高模** | **选人画面 + 奥义演出**（奥义真正生效的就是它） |
| `/PL/MODEL/2XXXBOD1.CCS` | 奥义"变体" | 实测**常常无效**，不要指望它 |
| `/PL/2XXXCHA0/1.CCS` | 招式特效件 | 一般不动 |
| `/BUDDY/2XXXBDY*.CCS` | 支援出场模型 | 仅当角色作为支援出场时才用 |
| `/CUTIN/1XXXCUTIN.CCS` | 奥义 cut-in | **只有动画+相机**，见第 3 节 |

**奥义层层递进（血泪教训）**：先换战斗 → 用户验证战斗外观 → 再补 `MODEL` + `1P`。
只换 `MODEL` 会得到"奥义没变化"，那是正常的——奥义读的是 `1P`。

## 3. 奥义 cut-in 的机制（不需要单独换）

拆开 `/CUTIN/1XXXCUTIN.CCS`（gzip 后只有 4~5KB）会看到它**没有 Model / Texture / Clump**，
只有：

- 每根骨骼一个 `ExternalObject`（`OBJ_1xxx00t0 <骨名>` 占位，12 字节）
- `AnimationObject`（20 字节/根）
- `Material`（眼/嘴）、`Camera`（`CAM_xxx_camera1/2`）
- 一个 `Animation` 块（如 `ANM_1krw_cutin`，25 帧）

它引用的骨名是 `l finger41`、`muffler1`、`cloth1` 这类——**正是 1P 骨架的骨名**。
结论：**奥义 cut-in 复用角色的 1P 模型**，CUTIN 文件只提供"怎么动 + 怎么拍"。
所以 **1P 换好以后，奥义演出的外观就已经跟着变了**，不需要单独改 CUTIN。

（若确实想让奥义播放**来源角色自己的 cut-in 动作**，需要把 `ANM_*` 的轨道从来源骨架布局
重映射到目标骨架布局，并改写所有 `OBJ_` 名字——工作量大且容易崩；而且"保留目标动作"
本身通常就是需求，一般没必要。）

## 4. CCS 格式要点

**容器**：头（`ccsHeader` + `ccsIndex` + Setup 区）+ 一串块 + Stream 块 + 尾部。
每块 8 字节头：`u16 type` / `u16 0xCCCC` / `u32 (rec/4)`，随后是数据。
类型：`Object 256`、`Material 512`、`Texture 768`、`Clut 1024`、`Camera 1280`、
`Animation 1792`、`Model 2048`、`Clump 2304`、`ExternalObject 2560`、
`BoundingBox 3072`、`AnimationObject 8192`、`Stream 5`（末尾）。

**Model 头**：`u32 名字编号` + `f32 vertexScale` + `u8 type` + `u8 flags` + `u16 meshCount`
+ 8 字节杂项 + `outline(4+4)` + `lookupList(llcount 字节, 4 对齐)`；空模型共 28 字节。

**DeformableMesh**：`u32 materialIndex` + `u32 vc` + `u32 dc`；
`dc==0`（单权重）：`+u32 boneSlot` → xyz `i16×3×vc` → 4 对齐 → 法线 `i8×4×vc` → UV `i16×2×vc`；
`dc>0`（多权重）：`vp 4×i16(x,y,z,param)×dc` + 法线 `i8×4×dc` + UV `i16×2×vc`。

**★ 顶点里的骨骼编号是「lookup 槽位」，不是骨架位置。**
`lookupList` 把槽位映射到**骨架位置**。替换时：
- 顶点数据**一个字节都不改**；
- 只把 `lookupList` 的内容由「S 的骨架位置」翻译成「T 的骨架位置」。

**rec 惯例**（照抄，别自创）：Model `rec = 数据 + 1140`（身体）；
空模型/头发 `rec = 数据 + 120`；Texture `rec = 数据 + 200`；Clut `rec = 数据`。
通用做法：`新 rec = 新数据长度 + (原块 rec − 原块 consumed)`。

## 5. 骨架名字映射

**位置号 = `clump.boneIndices` 的 enumerate 序号**（不是名字表编号！）。
骨名先 `norm()`：`'OBJ_2szw00t0 head' -> 'head'`（去掉第一个 token）。

- 骨名唯一时：`name_pmap()`（先到先得）。
- **左右骨骼同名时（1P 高模几乎总是如此）必须用 `occ_pmap()`**：
  来源里第 N 个叫 `clavicle` 的骨 → 目标里第 N 个叫 `clavicle` 的骨。
  用"先到先得"会把左右手臂都绑到同一根骨上 → 模型塌成一团。
- 目标骨架没有的骨（如静音的衣摆 `tail/tail1/tail2`）：绑到 **pelvis** 最自然
  （多套验证过的选择），或目标的 `body` 骨。

**踩坑**：位置号写成名字表编号 ⇒ lookup 出现上千索引 ⇒ 模型全崩。

## 6. 三个变体各自换什么

**战斗 `2XXXBOD1`**
- body：名字编号 → T 的；`lookupList` 走 pmap；每个子网格 `materialIndex` → T 的 MAT 编号
- body 贴图：换内容（名字编号 → T 的、内部 clut 指针 → T 的 CLUT 编号）
- CLUT：换内容（`u32 index` → T 的编号）

**MODEL `MODEL/2XXXBOD1`**：目标可能有**两个 body**（`00t0` 与 `05t0`，各带自己的贴图与
3 个 CLUT）。两个都要换，否则某些配色仍是原角色。编号常与 T 天然对齐。

**1P `1XXXBOD1`**
- body：同上（1P 骨数更多，必须按名字映射，且要用 occ_pmap）
- body 贴图 / CLUT：换内容
- **眼/嘴刚性小件（eye1/eye2/mou1）**：只移植**几何**；
  `[0] 名字编号`、`[28] parent`、`[32] material` **一律保留 T 原件值**！
  （parent 引用配套 `_0` 块；写错 ⇒ 选人后进战斗即崩。）
- eye/mou 贴图的名字编号与 clut 指针**常常两边不同**，必须逐项核对改写。

## 7. ★ 容量约束（最容易翻车的地方）

原位补丁要求 **新 gz ≤ 原文件 size**。extent 富余通常只有几十~一千字节。

```powershell
# extent 富余 = 下一个文件的 LBA*2048 - (本文件 LBA*2048 + size)
```
- 差额很小（几 KB）时，可试 `zlib` level 9 + memLevel 9 重新压。
- 差额较大时**腾空间**：把 T 文件里**非主外观用途**的块置空
  （典型：次要 body、另一形态 body、头发）。置空必须照抄
  **同文件里真实存在的空模型块**（`rec == 28 且 consumed == 28`）的 28 字节，
  只改名字编号；`新 rec = 28 + (该块原 rec − consumed)`。
  （真实空模型头尾部是 `outline = (-0.0, 1.0)`，即 `00 00 00 80 00 00 80 3f`；**别自己拼全零**。）
- **源模型比目标大就可能根本塞不下**。例：反方向"静音显示夕日红"时，夕日红 1P body
  122,096B 比静音的 84,168B 大，压缩后仍超约 20KB，不可能塞入。
  此时**如实告知用户换方向**（反方向通常就放得下），不要硬塞——
  硬塞会覆盖磁盘上下一个文件，损坏镜像。

## 8. 重建、校验与原位补丁

按块重建：`头 + 每块(8B 头 + 数据) + Stream 块(8B 头 + rec 字节) + 尾部`；
未替换的块**原样复制**。然后：

1. `readCCS` 重解析 + 再走一遍块表：块数/顺序/名字必须与原文件一致；
2. 断言 `meshCount` / `lookupListCount` / `lookupList` / 每个 mesh 的 material / 贴图 clut；
3. 走到 EOF；
4. `len(gzip.compress(out, 9)) <= 原 size`。

打包（`patch_inplace.py`）：
```python
off = (210454 + 3 + innerLBA) * 2048
# 复制原盘 → 在 off 写 gz + b'\x00'*(size-len(gz))（尾补零，保持 size 不变）
```
**绝对不要重建 CVM**（不带标志的 mkcvm 会写出未加密卷 ⇒ 黑屏）；
也不要改 UDF/PVD/目录记录。只改 ZONE 负载里的文件字节。

## 9. 交付前验证（每次都要）

1. **全盘比对**：MOD 版与原版逐扇区比，差异**恰好**是那几段 span 的偏移；
2. 段内回读：写回后 `read` 校验 `gz` 前缀 + 全零尾；
3. 在**原版** ISO 的同一偏移 gunzip，签名应等于目标文件（证明 LBA→offset 正确）；
4. 可选：全盘搜该 gz 流指纹（头 64 字节）应**只出现一次**（多于一次说明有副本）。

## 10. 用户测试要点

- 必须**冷启动**模拟器（不要读战斗中的即时存档，模型不会重新加载）；
- 选**目标角色** → 进战斗看外观；开奥义看特写；看选人画面；
- 招式/动作不变才正确；崩 = 结构问题（优先查 1P 眼嘴件 parent/material）；
- 某个画面仍是原角色 = 对应变体没生效（**优先怀疑 1P**）。

## 11. 排错清单（"改了没生效"）

1. **先确认方向**：是不是把源和目标搞反了？（最常见：改了来源角色的文件，
   却去选目标角色看效果。）
2. **证明补丁真的在盘上**：在 `outer_offset` 处从原版与 MOD 版各读 `size` 字节，
   两者应不同、且都能 gunzip、签名正确。
3. 确认"没生效"的是哪个画面：战斗 = `2XXXBOD1`、奥义/选人 = `1XXXBOD1`。
   只改了战斗却盯着奥义看 ⇒ 正常现象，不是 bug。
4. 确认用户测的是新 ISO、且**冷启动**（非即时存档）。
5. 检查置空块是否用了自己拼的"空模型头"——改用同文件真实模板。
6. 全盘搜 gz 指纹确认没有第二份副本；也没有未压缩副本
   （在 ISO 里搜 `CCSF2xxx` 字符串，命中即说明存在明文副本）。

---

## 附：脚本命名惯例

```
_analyze_<SRC>_<DST>.py      结构/骨架/索引 dump
_swap_battle_<DST>_<SRC>.py  战斗版
_swap_model_<DST>_<SRC>.py   MODEL 版
_swap_1p_<DST>_<SRC>.py      1P 版（含眼嘴件）
_patch_<DST>_<SRC>_mod.py    原位补丁打包
_audit_<DST>_<SRC>.py        全盘比对验证
```
（`<DST>` = 保留动作的目标角色，`<SRC>` = 外观来源角色。）
