# 澳门彩生肖助手

本地娱乐工具：抓取开奖历史与站点推荐文，**同时给出包肖与特码生肖各一个最看好**。

> **包肖**：6 平码 + 1 特码中，**任意一个**是该生肖即算中。  
> **特码生肖**：只有特码是该生肖才算中。  
> 开奖近似随机，网站推荐可信度低。本工具不承诺盈利，请理性使用。

站点列表与开关：[`app/sites.py`](app/sites.py)（含旧站 + `网站.md` 新站）。  
探测备注：[`网站.md`](网站.md)。

## 环境

- Python 3.10+
- MySQL（库 `aomencai` 需已创建）
- 连接默认：`127.0.0.1:3306` / `root` / `1234` / `aomencai`

## 一、建表（只跑一次）

库已存在时执行（**务必 UTF-8**，避免注释变成 `???`）：

```powershell
# 推荐：用 Python 导入，编码最稳
cd e:\GrammarPractice\AiProject\Aomencai
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "e:\GrammarPractice\AiProject\Aomencai"
python -c "from pathlib import Path; import pymysql; from app.config import settings; sql=Path('sql/schema.sql').read_text(encoding='utf-8'); conn=pymysql.connect(host=settings.db_host,port=settings.db_port,user=settings.db_user,password=settings.db_password,charset='utf8mb4',autocommit=True); cur=conn.cursor(); cur.execute('SET NAMES utf8mb4');
[cur.execute(s) for s in sql.replace('USE aomencai;','').split(';') if s.strip()]; conn.close(); print('schema ok')"
```

若注释已乱码，执行修复：

```powershell
python -m scripts.fix_comments
```

## 二、安装依赖

在项目根目录 `Aomencai`：

```powershell
cd e:\GrammarPractice\AiProject\Aomencai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## 三、启动

在**项目根目录**执行（不要停在 `.venv\Scripts` 里直接敲 `uvicorn`）：

```powershell
cd e:\GrammarPractice\AiProject\Aomencai
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "e:\GrammarPractice\AiProject\Aomencai"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

若未激活 venv、人在 `Scripts` 目录，需写成：

```powershell
cd e:\GrammarPractice\AiProject\Aomencai
$env:PYTHONPATH = "e:\GrammarPractice\AiProject\Aomencai"
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开：http://127.0.0.1:8000

> 需要热重载时可加 `--reload`；日常用上面命令即可。

## 四、怎么用

1. 打开面板后，默认**只读数据库**（不会每次自动狂抓网站）。
2. 首次或每天开奖前，点 **「刷新分析」**：
   - 抓历史开奖 + 最新开奖
   - 抓两站当期推荐文
   - 重算并展示 **包肖** 与 **特码生肖** 各一个最看好
3. **「仅读库刷新」**：不抓站，只重新加载已有结果。
4. 也可命令行全量刷新：

```powershell
$env:PYTHONPATH = "e:\GrammarPractice\AiProject\Aomencai"
python -m app.jobs.bootstrap
```

## 五、接口

- `GET /api/health` 健康检查
- `GET /api/latest-recommend` 最新包肖 + 特码推荐
- `GET /api/draws` 最近开奖
- `POST /api/refresh?full_history=true` 抓取并分析

## 说明

- 表结构固定；开奖/推荐/推荐结果是动态数据。
- 「站点历史命中率回测」留作升级项，第一版未做。
