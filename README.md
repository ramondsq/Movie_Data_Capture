<h1 align="center">Movie Data Capture</h1>

![](https://img.shields.io/badge/build-passing-brightgreen.svg?style=flat)
![](https://img.shields.io/github/license/yoshiko2/Movie_data_capture.svg?style=flat)
![](https://img.shields.io/github/release/yoshiko2/Movie_data_capture.svg?style=flat)
![](https://img.shields.io/badge/Python-3.10+-yellow.svg?style=flat&logo=python)

**本地电影元数据抓取工具 | 刮削器**，配合 Emby, Jellyfin, Kodi 等本地影片管理软件使用，自动抓取元数据（metadata）并分类整理本地影片。

## 安装

需要 Python 3.10+，推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync
```

## 使用

```bash
# 扫描并处理当前目录（或 config.ini 中配置的目录）
uv run python -m mdc

# 搜索单个番号（仅查看元数据，不移动文件）
uv run python -m mdc -s ABCD-123

# 指定来源
uv run python -m mdc -s ABCD-123 -S javbus

# 开启调试模式
uv run python -m mdc -g
```

详细参数请参考 `uv run python -m mdc --help`。

## 配置

编辑 `config.ini` 进行配置，主要选项：

- `main_mode`：1=刮削+整理, 2=仅整理, 3=仅刮削（不移动文件）
- `source_folder`：影片来源目录
- `success_output_folder`：成功输出目录
- `sources`：刮削来源优先级

更多配置说明请参考 [官方 WIKI](https://github.com/yoshiko2/Movie_Data_Capture/wiki)。

## 支持的来源

javbus, javdb, javlibrary, fanza, dmm, mgstage, fc2, carib, caribpr, dlsite, getchu, gcolle, avsox, jav321, javday, javmenu, madou, msin, pcolle, pissplay, tmdb, imdb 等。

## 申明

当你查阅、下载了本项目源代码或二进制程序，即代表你接受了以下条款：

- 本项目和项目成果仅供技术、学术交流和 Python 性能测试使用
- 用户必须确保获取影片的途径在用户当地是合法的
- 运行时和运行后所获取的元数据和封面图片等数据的版权，归版权持有人持有
- 本项目不提供任何影片下载的线索
- 禁止将获取到的数据用于商业目的或提供给可能有非法目的的第三方
- 用户在使用前请了解并遵守当地法律法规
- 法律后果及使用后果由使用者承担
- [GPL LICENSE](https://github.com/yoshiko2/Movie_Data_Capture/blob/master/LICENSE)
- 若用户不同意上述条款任意一条，请勿使用本项目和项目成果

## 贡献者

[![](https://opencollective.com/movie_data_capture/contributors.svg?width=890)](https://github.com/yoshiko2/movie_data_Capture/graphs/contributors)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=yoshiko2/Movie_Data_Capture&type=Date)](https://star-history.com/#yoshiko2/Movie_Data_Capture&Date)
