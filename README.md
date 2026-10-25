# 澳门彩生肖助手

本地娱乐工具：抓取开奖历史与站点推荐文，每期给出**单肖、三连肖、五连肖、特码生肖**四种推荐，各记各的中没中。

> **单肖**：固定为当年肖（占 5 个号的那一只；2026-02-17 起是马）。7 个号码里出现即中。  
> **三连肖 / 五连肖**：当年肖放第一，其余名额按旧的遗漏、热度、资料分往下排。三只或五只全部出现才算中。  
> **特码生肖**：只有特码是该生肖才算中。仍用旧公式，资料不进排名。  
> 开奖近似随机，网站推荐可信度低。本工具不承诺盈利，请理性使用。

站点列表与开关：`[app/sites.py](app/sites.py)`（含旧站 + `网站.md` 新站）。  
探测备注：`[网站.md](网站.md)`。

## 环境

- Python 3.10+
- MySQL（库 `aomencai` 需已创建）
- 连接信息放在项目根目录的 `.env`（已被 git 忽略）。第一次用先复制一份：

```powershell
Copy-Item .env.example .env
# 再把 DB_USER / DB_PASSWORD 改成自己的
```

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

浏览器打开：[http://127.0.0.1:8000](http://127.0.0.1:8000)

> 需要热重载时可加 `--reload`；日常用上面命令即可。



## 四、怎么用

1. 打开面板后，默认**只读数据库**（不会每次自动狂抓网站）。
2. 每天点两次 **「刷新分析」**：开奖前 21:00–21:20 一次定推荐，21:32 开奖后一次对账。每次会：
  - 抓历史开奖 + 最新开奖
  - **自动对账**已开期推荐 / 各站 tip 命中（三连肖、五连肖只自动对账，不手填）
  - 抓站点当期推荐文（包肖资料按 0.15 参与排名，差站只缩放这一档；特码资料只抓取和对账，不进排名）。全部站抓完再替换，某个站这次没抓到就沿用它上次的名单
  - 重算并展示单肖、三连肖、五连肖、特码生肖。已有中没中的期不再改
3. **「仅读库刷新」**：不抓站，只重新加载已有结果。
4. 也可命令行全量刷新：

```powershell
$env:PYTHONPATH = "e:\GrammarPractice\AiProject\Aomencai"
python -m app.jobs.bootstrap
```

升级命中跟踪（已有库补字段）：

```powershell
python -m scripts.migrate_hit_tracking
python -m scripts.reconcile_hits
```



## 五、接口

- `GET /api/health` 健康检查
- `GET /api/latest-recommend` 最新四种推荐（含命中汇总、站点权重、公式对照）
- `POST /api/manual-hit` 开奖后手动改正单肖/特码中没中（已写入的不会被自动对账覆盖）
- `POST /api/reconcile` 仅回填尚未录入的对账
- `GET /api/draws` 最近开奖
- `POST /api/refresh?full_history=true` 抓取并分析



## 说明

- 表结构固定；开奖/推荐/推荐结果是动态数据。
- 号码对应的生肖按开奖日期所在的生肖年取，春节当天换年。春节日期表在 `app/services/zodiac.py`，到 2035 年，之后要补。
- 站点权重按近 N 期相对期望命中率缩放（样本少时接近 1，不剧烈抖动）。

