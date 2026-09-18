# 究极觉醒2角色模型替换

一个 **Agent Skill**：在 PS2《火影忍者疾风传 究极觉醒2》（Naruto Shippuuden: Narutimate Accel 2）
中把**某个角色的外观换到另一个角色身上**（保留动作/招式），并覆盖**战斗 + 奥义 + 选人**三处模型。

An agent skill for *surgically* swapping one character's appearance onto another in
**Naruto Shippuuden: Narutimate Accel 2 (PS2)** while keeping the target character's moves,
covering the battle model, the ougi/select high-detail (1P) model, and the ougi variant.

---

## 它解决什么问题 / What it solves

直接整文件替换角色模型会让游戏**进战斗卡死**（游戏按目标角色的动画编号去驱动来源角色的骨架，
骨骼编号对不上就崩）。这个 skill 记录的是经过多轮实机验证的正确做法：

- **外科手术**：只替换"外观相关块"（body 网格 / body 贴图 / 调色板 / 眼嘴刚性小件），
  骨架、动画、名字表、Stream 全部保留目标角色的；
- **原位补丁**：不重建 CVM（加密卷，重建会黑屏），把新文件的 gzip 写回它在 ISO 里的**原 extent**；
- 处理**跨骨架**的名字映射（含 1P 骨架左右骨骼同名的坑）、`lookupList` 槽位语义、
  rec 长度惯例、**容量约束**（源模型比目标大就可能塞不下）、以及**奥义 cut-in 机制**。

## 安装 / Install

把 `SKILL.md` 放到你的 skill 目录（按 skill 名建子目录）：

```powershell
# Windows PowerShell (DSH)
$d = "$env:USERPROFILE\.dsh\skills\究极觉醒2角色模型替换"
New-Item -ItemType Directory -Force $d | Out-Null
Copy-Item .\SKILL.md $d
```

```bash
# bash
mkdir -p ~/.dsh/skills/究极觉醒2角色模型替换
cp SKILL.md ~/.dsh/skills/究极觉醒2角色模型替换/SKILL.md
```

其它支持 `SKILL.md` + YAML frontmatter 的 Agent 运行时同理，放进对应的 skills 目录即可。

## 目录内容 / Contents

| 路径 | 说明 |
|---|---|
| `SKILL.md` | skill 本体：分步流程、踩坑与排错清单 |
| `tools/` | 通用化脚本模板（分析 / 换模 / 原位补丁 / 全盘校验），无硬编码路径 |
| `examples/` | 五份实机验证过的完整替换记录（含奥义修复与方向/容量两个坑） |

## 前置条件 / Prerequisites

- 一份**你自己的**游戏镜像（本仓库不含任何游戏数据、模型或镜像）。
- Python 3（`tools/` 只用标准库；渲染贴图识别角色额外需要 `numpy` + `pillow`）。
- 能从 `data.cvm` 取出内层 ISO，并生成 `inner_filelist.txt`（`路径 \t LBA \t gz长度`）。
- CCS 解析库：开源项目 `blender_ccs_importer` 的 `ccs_lib`。

## 声明 / Disclaimer

- 本仓库只包含**文档化的方法论与脚本模板**，不含任何游戏资源、模型、贴图或镜像。
- 仅用于**你自己拥有**的游戏副本的本地修改与学习用途。
- 相关商标与版权归各自权利人所有。
