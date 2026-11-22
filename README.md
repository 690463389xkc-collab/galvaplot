<p align="center"><img src="assets/icon.png" width="96" alt="GalvaPlot icon"></p>

<h1 align="center">GalvaPlot · 电池数据一键作图</h1>

<p align="center">把蓝电（LAND）<code>.cex</code> 或新威（Neware）<code>.ndax</code> 源文件拖进窗口，一键画出可以直接放进 PPT 和论文的电化学图。</p>

<p align="center">
  <a href="https://github.com/690463389xkc-collab/galvaplot/releases/latest"><img alt="最新版本" src="https://img.shields.io/github/v/release/690463389xkc-collab/galvaplot?label=%E4%B8%8B%E8%BD%BD&color=2f5f9e"></a>
  <img alt="下载量" src="https://img.shields.io/github/downloads/690463389xkc-collab/galvaplot/total?label=downloads">
  <img alt="平台" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS-555">
  <img alt="许可证" src="https://img.shields.io/github/license/690463389xkc-collab/galvaplot">
</p>

<p align="center"><img src="docs/demo.gif" width="900" alt="GalvaPlot 演示：拖入文件、改名称、切换图类型、单独查看子图、复制到 PPT"></p>

## 适合谁

做电池、电化学和材料方向的硕士生、博士生：测完电池，想马上把几个电池的充放电曲线、循环性能放在一张图里对比，放进组会 PPT，不想每次都导出 Excel 再到 Origin 里一列一列地复制。

## 能做什么

| 图 | 内容 |
|---|---|
| **充放电曲线** | 指定圈数的电压–容量曲线。可以每圈一个子图、比较不同电池，也可以每个电池一个子图、比较不同圈（颜色由浅到深） |
| **循环性能** | 放电/充电容量、库仑效率、能量效率、容量保持率、平均充/放电电压、ΔV，任选 1–8 个，自动排成多子图 |
| **电压–时间** | 整个测试过程的电压曲线，可叠加或每个电池一个子图，用来检查异常 |
| **dQ/dV** | 指定圈数的微分容量曲线，可调电压间隔和平滑 |

- **最多 10 个文件**同时对比，蓝电和新威的文件可以混在一起；支持直接拖入整个文件夹
- **曲线名称可随意改**：文件名再乱也没关系，双击改成图例里想要的名字；“精简名称”可以一键去掉日期和所有文件都有的部分
- 下标、上标不用学 LaTeX：`AlCl_{3}` → AlCl₃，`Li^{+}` → Li⁺
- 颜色、线型逐条可调（平行样可以同色、不同线型）
- 容量单位：mAh、mAh/g（填活性物质质量；新威文件里设置过的质量会**自动读入**）、mAh/cm²（填面积）、相对参考圈的 %
- 充放电曲线和 dQ/dV 有三种排布：每圈一个子图、每个电池一个子图、**所有圈+所有电池**（画在一张图里，颜色区分电池，线型区分圈数）
- 图下方可写**测试条件**（正极、电解液、电流密度…），每张图都带上
- 图中文字可选**英文或中文**
- 在预览图的某个子图上**点右键**：单独复制这个子图的数据（直接粘贴到 Excel / Origin）、复制或保存这个子图、只显示这个子图
- **复制图片**后直接粘贴到 PPT/Word；也可保存为 PNG（默认 300 dpi）、SVG、PDF、EPS、TIFF
- **导出数据**为 Excel：每条曲线两列，加上每个电池的逐圈数据，可直接导入 Origin
- **一键导出全部**：4 种图（PNG + SVG）和数据一次保存到一个文件夹
- 右下角**检查更新**，有新版本时给出下载链接
- 读取快：10 个 80 MB 左右的文件（共约 2000 万个数据点）约 1–2 秒读完

图的风格：Arial 字体、刻度朝内带次刻度、无边框图例、多子图自动加 a/b/c 编号，配色按色觉障碍友好的顺序排列。

## 下载安装（不用装 Python）

到本页右侧的 **[Releases](../../releases)** 下载最新版本（注意：不是绿色的 “Code → Download ZIP”，那是源代码）。

| 系统 | 下载哪个文件 | 怎么装 |
|---|---|---|
| **Windows 10/11（推荐）** | `GalvaPlot-版本号-Windows-Setup.exe` | 双击安装包，一路“Next”。默认只装给当前用户，**不需要管理员密码**；会建开始菜单项和桌面图标 |
| Windows 免安装版 | `GalvaPlot-版本号-Windows-x64-portable.zip` | **先完整解压**，再双击文件夹里的 `GalvaPlot.exe`（在压缩软件里直接双击会打不开）。适合放 U 盘或没有安装权限的电脑 |
| **macOS（Apple 芯片：M1–M5）** | `GalvaPlot-版本号-macOS-AppleSilicon.dmg` | 双击打开，把 GalvaPlot 图标拖到旁边的“Applications（应用程序）”文件夹；第一次打开见下面的说明 |

Intel 芯片的 Mac 和 Linux 暂时没有安装包，请用下面的“从源码运行”。

### 第一次打开时的提示（正常现象）

程序是免费开源软件，没有购买代码签名证书，所以系统会提示一次：

- **Windows**：出现“Windows 已保护你的电脑”时，点“**更多信息**”→“**仍要运行**”。
- **macOS**：提示“无法验证 / Apple 无法检查其是否包含恶意软件”（英文系统是 “Not Opened”）时，**点“完成 / Done”，不要点蓝色的“移到废纸篓 / Move to Trash”**（点了会把程序删掉，到废纸篓里拖回“应用程序”即可）。然后打开“**系统设置 → 隐私与安全性**”，在“安全性”一栏点“**仍要打开**”，输入开机密码。只需要这一次。安装窗口里也印着这几步：

  <img src="docs/first-launch-macos.png" width="560" alt="macOS 第一次打开：点完成，不要点移到废纸篓；系统设置 → 隐私与安全性 → 仍要打开">

  如果提示“**已损坏，无法打开**”，在“终端”里运行下面一行后再打开：
  ```bash
  xattr -dr com.apple.quarantine /Applications/GalvaPlot.app
  ```
- **360、火绒等安全软件**有时会把没有签名的 Python 程序误报为病毒。代码完全公开，可以在安全软件里选择“信任”或把安装目录加入白名单。
- 第一次启动要等 10–30 秒（建立字体缓存，会显示提示窗口），以后打开只要 1–2 秒。

### 更新到新版本

从 0.3.0 开始：点窗口右下角的“**检查更新**”，有新版本时点“**立即更新**”。程序会下载新版本，核对 GitHub 公布的校验值（SHA-256）无误后自动替换旧版本并重新打开，**不用再到系统设置里放行**（只有第一次安装需要）。原来的设置、曲线名称和质量都会保留，已拖入的文件需要重新拖入。

- 适用于：macOS 装在“应用程序”里的版本、Windows 用安装包装的版本。Windows 免安装版和从源码运行的，请手动下载替换或 `git pull`。
- 0.2.x 及更早的版本还没有这个功能，需要像第一次一样手动下载安装一次 0.3.0 或更新的版本：Windows 安装包会直接替换旧版本；macOS 把新的 GalvaPlot 拖进“应用程序”时选“替换”。
- 程序默认每天启动时最多自动检查一次，只向 GitHub 查询最新版本号（不上传任何数据或文件），可以在检查更新的窗口里关掉。只有你点了“立即更新”才会下载和安装。
- 为什么不用再放行：系统只给浏览器下载的文件打“来自网络”的标记，程序自己下载的更新没有这个标记。作为替代，程序在安装前核对校验值，下载不完整或被篡改就不安装；这依赖于本仓库的发布页面没有被他人篡改。

### 卸载

- Windows：“设置 → 应用 → 已安装的应用”里找到 GalvaPlot 卸载；免安装版直接删除文件夹。
- macOS：把“应用程序”里的 GalvaPlot 拖到废纸篓。

## 三步出图

1. 把 `.cex` / `.ndax` 文件拖进窗口（或点“添加文件…”）。没有数据可以先点“示例数据”试试。
2. 在左侧双击修改名称；需要比容量就填“质量 mg”（新威文件里设置过质量的会自动填好）。
3. 在右侧选图的类型和圈数，点“复制图片”粘贴到 PPT，或“保存图片…”。

## 计算方法（请在论文/组会中按需说明）

| 量 | 定义 |
|---|---|
| 循环 | 蓝电：沿用文件里记录的循环号。新威：按工步程序里的“循环”步划分——循环开始前的充放电（例如首次放电）算第 1 圈，之后循环每执行一遍算一圈，与蓝电的编号方式一致；可能与 BTSDA 显示的循环号不同 |
| 充电/放电容量 | 同一循环内所有充电（或放电）工步容量之和；静置不计 |
| 库仑效率 | 默认 = 放电容量 ÷ 充电容量（同一循环）；负极半电池可在“更多设置”里改为 充电 ÷ 放电 |
| 能量效率 | 与库仑效率同方向，用能量计算 |
| 平均电压 | 工步能量 ÷ 工步容量 |
| ΔV | 平均充电电压 − 平均放电电压 |
| 容量保持率 / % 单位 | 放电容量 ÷ 参考圈放电容量；参考圈默认是第一个有放电的循环 |
| dQ/dV | 电压每变化设定值（默认 5 mV）取一个点做差分，再做滑动平均；放电为负值 |
| 未完成的最后一圈 | 最后一圈比上一圈少工步，或最后一步既没到截止电压、也没到上一圈的时长/容量，就视为“可能未完成”（测试仍在进行或中途停止），循环图中默认不画，界面下方会提示；可在“更多设置”里保留 |

只有画图时会对曲线抽点（电压–时间图），所有计算都用完整的原始数据。

## 支持的文件

- **蓝电 `.cex` 源文件**。`.icex` 是索引文件，不含数据，请拖同名的 `.cex`。
- **新威 `.ndax` 源文件**（BTS 8.x 写出的版本，内部格式 v17）。旧版 `.nda` 和其他版本的 `.ndax` 暂不支持，程序会提示；可以在 BTSDA 里导出 Excel 再拖进来。辅助通道（温度等）暂不读取。在测试软件里设置过的活性物质质量会自动读入（来自工步文件 `Step.xml` 的 `SCQ` 项，按 µg 换算为 mg：在 15 个设置了质量的参考文件上，按这个单位换算后程序设定的电流都正好是 100 mA/g 或 200 mA/g，据此确定单位），可以在表格里修改。
- 蓝电软件导出的 **Excel / CSV / TXT**（实验功能）：程序按表头自动识别“电压、电流、时间、容量、循环号、工步号、工步状态”等列，中英文表头都可以，单位从表头读取（V/mV、A/mA/μA、Ah/mAh、s/min/h）。请抽查几个循环的容量是否与蓝电软件一致。

### 关于文件格式（请务必读）

蓝电和新威都没有公开源文件格式，本程序的读取方法是**逆向得到的**：

- **蓝电 `.cex`**：用一个实验室蓝电测试仪的 143 个文件（共约 7600 万个数据点）做过内部一致性检查：记录的容量与 ∫|I|dt、能量与 ∫V|I|dt 一致，设定电流与实测电流一致，充放电工步的电流符号正确；并与独立编写的另一版解析器逐文件比对一致。
- **新威 `.ndax`**：用 BTS Client 8.0 写出的 26 个文件检查过：331 个充放电工步的记录容量与 ∫|I|dt 的比值中位数为 1.000000，能量与 ∫V|I|dt 一致（差异来自 30 s 采样间隔），所有数据点的电流符号与工步类型一致，重建的测试时间与记录里的系统时间一致（差 ≤ 77 s，系统时间只精确到秒）。
- **都还没有与官方软件导出逐点比对**。参考文件里只有静置、恒流充电、恒流放电三种工步；遇到恒压、恒流恒压、脉冲等其他工步，程序按电流方向判断充电/放电/静置，并在界面上提示。
- 重要数据（尤其是论文数据）请与蓝电 / BTSDA 软件核对。

如果你的文件读不了或结果不对，欢迎[提交 issue](../../issues)，最好附上文件（或用测试数据复现的文件）和蓝电软件中的对应数值，我们会尽快适配。

## 从源码运行

需要 Python 3.9 或更高版本：

```bash
git clone https://github.com/690463389xkc-collab/galvaplot.git
cd galvaplot
python -m pip install -r requirements.txt
python -m galvaplot
```

运行测试（不需要真实数据，测试用程序自带的合成数据）：

```bash
python -m unittest discover -s tests -v
```

自己打包：

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm galvaplot.spec                                            # 程序本体（dist/）
bash tools/make_dmg.sh dist/GalvaPlot.app dist/GalvaPlot-0.3.2-macOS-AppleSilicon.dmg   # macOS 安装镜像
```

Windows 安装包用 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 制作：`ISCC.exe /DMyAppVersion=0.3.2 installer\galvaplot.iss`。

发布新版本：改 `galvaplot/__init__.py` 里的版本号，推送 `v*` 标签（例如 `v0.2.0`），并在 `docs/release-notes/` 里放同名的发布说明（例如 `v0.2.0.md`）。GitHub Actions 会在 Linux 和 Windows 上跑测试，然后自动生成 Windows 安装包、Windows 免安装 zip 和 macOS dmg，并模拟用户安装后再自检一遍（Windows：静默安装 → 运行 → 卸载；macOS：挂载 dmg → 拷出程序 → 运行），全部通过才上传到 Releases。

## 项目结构

```
galvaplot/
  readers/land_cex.py   蓝电 .cex 读取（格式说明见文件开头）
  readers/neware_ndax.py 新威 .ndax 读取（格式说明见文件开头）
  readers/tabular.py    Excel / CSV 导入（实验功能）
  analysis.py           逐圈指标、充放电曲线、dQ/dV
  plotting/figures.py   4 种图；plotting/style.py 字体、配色
  plotting/export.py    Excel 导出
  gui/                  PySide6 界面
  demo.py               合成示例数据（也用于测试）
  updates.py            检查更新（只访问 GitHub Releases）
  self_update.py        程序内更新：核对校验值后替换旧版本
installer/galvaplot.iss  Windows 安装包脚本（Inno Setup）
tools/make_dmg.sh       macOS dmg 制作脚本（窗口布局来自 assets/dmg/template.dmg）
tools/make_dmg_art.py   dmg 背景和首次打开说明图；改完后运行 tools/make_dmg_template.sh 重做模板
tests/                  单元测试
```

## 参与贡献

欢迎提交 issue 和 pull request，尤其是：其他型号或软件版本的 `.cex` / `.ndax` 文件适配、新的图类型、英文界面。提交代码前请先跑一遍测试。

## 引用

如果 GalvaPlot 对你的研究有帮助，可以在论文的方法部分注明作图工具，例如“数据使用 GalvaPlot v0.3.2 处理和作图”。仓库页面右侧的 **Cite this repository** 提供 APA / BibTeX 格式（来自 [CITATION.cff](CITATION.cff)）。

## 许可与声明

- 开源协议：[MIT](LICENSE)。
- 本项目是个人开源项目，与武汉市蓝电电子股份有限公司、深圳市新威尔电子有限公司无关；“蓝电”“LAND”“新威”“Neware”是其各自所有者的商标。
- 程序按“现状”提供，计算结果请自行核对。

---

### English summary

**GalvaPlot** is a small desktop app for battery researchers. Drag up to 10 raw battery-tester files (LAND `.cex`, Neware `.ndax` from BTS 8.x) into the window and get publication-style figures in one click: voltage profiles, cycling metrics (capacity, coulombic/energy efficiency, retention, average voltages, ΔV), voltage vs time and dQ/dV. Curve names are editable (with `X_{sub}` / `X^{sup}` shortcuts), figures can be copied straight into PowerPoint or saved as PNG/SVG/PDF/EPS/TIFF, and plotted data can be exported to Excel; right-click a sub-plot to copy just its data. Profiles and dQ/dV can also be drawn with all cycles of all cells in one panel, and the active mass stored in Neware files is read automatically. A "check for updates" link queries GitHub Releases (at most once a day automatically; can be switched off). Both readers are reverse-engineered and checked for internal consistency (143 `.cex`, 26 `.ndax` files), but not yet against official exports — please verify important numbers. A Windows installer (per-user, no admin rights needed), a portable Windows zip and a macOS (Apple Silicon) disk image are on the Releases page; otherwise `pip install -r requirements.txt && python -m galvaplot`. MIT licensed; not affiliated with LAND or Neware.
