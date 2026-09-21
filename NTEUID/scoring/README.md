# NTEUID 评分系统

NTEUID 里"角色评多少分、评什么级"不是写死的。出图、练度统计、排行、AI 问答只认本目录定义的契约(`contract.py`),分数怎么算出来它们不关心。内置的「词条折算」(`providers/roll_value.py`)只是默认算法——你可以装别人写好的评分包换掉它,也可以自己写一个:伤害期望、自定义公式、甚至调外部服务算分,都行。

## 这套东西长什么样

```text
NTEUID/scoring/
├── README.md          # 本文档
├── contract.py        # 契约:评分包要实现什么
├── registry.py        # 注册、加载、切换、评级徽章渲染
├── providers/         # NTEUID 内置算法
│   ├── roll_value.py
│   └── assets/
└── scorers/           # 外置评分包都装这里(.gitignore 忽略,更新 NTEUID 永不冲突)
    └── my_pack/       # 一个评分包 = 一个独立 git 仓库,仓根就是 Python 包
        ├── __init__.py    # 入口,导入即注册
        ├── assets/        # 评级素材,可选
        └── data/          # 评分数据,可选
```

`scorers/` 下可以同时装任意多套,配置选中哪套用哪套。目录不存在会自动创建,不用预建。

## 我只想换个算法(使用者)

### 外置评分包列表

- [NTE-score-yuye](https://github.com/lingweiliang2510579032/NTE-score-yuye) — `scorer_id`: `yuye`
- [NTE-score-JiaBaili](https://github.com/jiabaili-qwq/NTE-score-JiaBaili) — `scorer_id`: `JiaBaili`

### 安装与切换

1. 复制上方 `NTE-score-yuye` 的仓库地址,发送 `ntescorer增加 <Git 仓库地址>` 安装评分包。
2. 重启 Bot,让 NTEUID 扫描并注册新安装的 Python 包。
3. 发送 `ntescorer查看`,确认已注册算法中出现 `yuye`。
4. 发送 `ntescorer设置 yuye` 切换算法。
5. 发送 `nte刷新面板`,按新算法重新计算并写入分数。

这里 `NTE-score-yuye` 是安装后的**包目录名**,用于 `ntescorer更新 NTE-score-yuye` 和 `ntescorer删除 NTE-score-yuye`;`yuye` 是包内注册的 `scorer_id`,用于 `ntescorer设置 yuye`。`ntescorer更新` 不带包名会更新全部 Git 安装的评分包。更新会强制对齐远端并丢弃评分包内的本地修改;如果更新包含 Python 代码,完成后还要重启 Bot。

角色面板、练度统计、评分排名、最强排行、AI 查询全部自动跟随,不用改任何代码。切换算法后旧算法的分数会自动退出榜单(见文末"榜单隔离"),用户重新「刷新面板」即可按新算法入榜。

## 我要写一个评分包(作者)

先看一个完整能跑的最小示例,就是 `scorers/my_pack/__init__.py` 一个文件:

```python
from dataclasses import dataclass

from ...contract import GradeSpec, BaseScorer, ScorerMeta
from ...registry import register_scorer
from ....utils.sdk.tajiduo_model import CharacterDetail, CharacterProperty


@dataclass(frozen=True, slots=True, kw_only=True)
class _Item:
    item_id: str
    display: str  # 装备卡上的分数文本,格式随意,建议 ≤8 个全角字符
    grade: str | None  # 单件评级;None 就不画徽章
    unlocked_subs: int  # 已解锁副词条数,游戏规则是 lev // 5


@dataclass(frozen=True, slots=True, kw_only=True)
class _Result:
    score: float  # 总分,原样入库、排序并显示在榜单;可带小数,整数也可直接返回
    display: str  # 角色卡上的总分文本,格式随意:"87分"、"毕业度92.5%"
    grade: str  # 总评级,必须出自 grades() 词表
    equipment: tuple[_Item, ...]

    # 三个判定驱动角色卡的词条高亮;不想区分就全 False,卡片全白,不报错
    def is_role_prop_effective(self, prop: CharacterProperty) -> bool:
        return False

    def is_main_prop_counted(self, prop: CharacterProperty) -> bool:
        return False

    def is_sub_prop_recommended(self, prop: CharacterProperty) -> bool:
        return False

    # 可选:自定义已判定为高亮的词条颜色;不写此方法就使用 NTEUID 默认紫色
    def highlight_color(self, prop: CharacterProperty, locked: bool) -> tuple[int, int, int] | None:
        return (255, 145, 238) if locked else (255, 0, 235)


class MyScorer(BaseScorer):
    scorer_id = "my_pack"
    meta = ScorerMeta(author="你的名字", name="我的评分", version="0.1.0")

    def grades(self):
        # 没有素材图就只给颜色,渲染端自动画「圆底+文字」徽章
        return (GradeSpec(id="优", color=(255, 167, 38)), GradeSpec(id="良", color=(91, 155, 213)))

    async def score_character(self, character: CharacterDetail):
        items = (*character.suit.core, *character.suit.pie)
        if not items:
            return None  # 没装备 → 展示为 --分
        equips = tuple(
            _Item(item_id=i.id, display=f"{i.lev}级", grade="优" if i.lev >= 15 else "良", unlocked_subs=i.lev // 5)
            for i in items
        )
        total = sum(i.lev for i in items)
        return _Result(score=total, display=f"{total}分", grade="优" if total >= 60 else "良", equipment=equips)


register_scorer(MyScorer())
```

把这个目录放进 `scorers/`,配置切到 `my_pack`,所有卡片就已经在用你的分数了。下面是你写真实算法时需要知道的事。

### 导入怎么写

评分包会被挂载成 `scoring.scorers.<包名>`,所以相对导入的点数和磁盘目录层级一一对应,IDE 和类型检查都能正常解析:

- 契约和注册:`from ...contract import ...`、`from ...registry import register_scorer`
- 插件的模型和工具:`from ....utils.sdk.tajiduo_model import CharacterDetail`

不要写 `from gsuid_core....` 绝对导入——部署环境里插件包名不固定,绝对导入会碎。

### 每个方法管什么

- `scorer_id`:稳定唯一的 ID。它会写进每条评分记录,换 ID 等于换算法(旧记录退出榜单),所以定了就别改。
- `meta`:`ScorerMeta(author=...)` 必填 author,注册时校验;name / version / updated_at / description 可选。激活时会打进日志,方便部署者确认在用哪个包哪个版本;`description` 非空时会显示在练度统计标题区右侧,评分排行标题下方则显示为「description · 上榜范围与数量」,超出单行宽度会自动截断。
- `grades()`:本算法用到的**全部**评级。`ScoreResult.grade` 和单件 `grade` 都必须出自这个词表,词表外的评级不画徽章、文字纯白。
- `score_character(character)`:核心方法。没有该角色的方案、或者没装备,返回 `None`(展示为 `--分`);自己的数据文件损坏就抛 `ValueError`。方法是 async 的,做 HTTP / 数据库 / 伤害引擎调用都可以——但调外部服务请自带超时,这个方法卡住会卡住整个「刷新面板」。
- `score` 与 `display`:`score` 是数据库和榜单使用的数值,可带小数(如 `320.35`),会原样参与排行并显示;整数评分包直接返回整数即可,显示时不会多出 `.0`。角色卡的大字总分使用 `display`,可自行展示 `"87分"`、`"毕业度92.5%"` 等文本。
- `highlight_color(prop, locked)`:可选方法,无需继承额外基类。只有三个判定方法已经认定需要高亮的词条才会调用它;`locked=True` 表示尚未解锁的装备副词条。返回 RGB 三元组即可自定义颜色,返回 `None` 则该词条使用默认色;完全不实现时,普通高亮使用 `(255, 0, 235)`,未解锁高亮使用 `(255, 145, 238)`。它只控制颜色,不改变哪些词条被高亮。
- `equipment`:必须与 `(*suit.core, *suit.pie)` **等长同序**,一件对一件,数量对不上会直接报错,不会静默画错。
- `score_batch(characters)`:练度统计和刷新面板落库时几十个角色一批调它。`BaseScorer` 默认逐个调 `score_character` 并把单角色的 `ValueError` 降级成 `None`,通常不用管。覆盖成合批请求时,同样等长同序,并保留单角色失败降级为 `None` 的语义——整批抛异常会让整个账号落库失败。
- `describe_char(char_id)`:给 AI 知识库的文字说明(这个角色怎么算分、什么词条有效)。**插件 import 期就会被调,不能依赖 prepare**;没有该角色的方案返回 `""`。
- `prepare()` / `close()`:激活时和停用时各调一次,由 registry 驱动,不要自己调。加载数据、建连接放 prepare;prepare 抛异常则维持旧算法不变。清缓存、断连接放 close——通过 `ntescorer更新` 更新数据后,切走再切回来就能重新加载。

### 数据文件放哪、怎么读

数据随包分发,放包内 `data/`,用 `Path(__file__).parent` 定位。多角色单 JSON 和多角色多 JSON 都常见:

```python
import json
from pathlib import Path
from functools import lru_cache

_DATA = Path(__file__).parent / "data"


# 写法一:所有角色一个 JSON({char_id: {...}}),prepare 时整个载入
class SingleJsonScorer(BaseScorer):
    def __init__(self) -> None:
        self._plans: dict[str, dict] = {}

    async def prepare(self) -> None:
        self._plans = json.loads((_DATA / "plans.json").read_text(encoding="utf-8"))

    async def close(self) -> None:
        self._plans = {}


# 写法二:一个角色一个 JSON(data/chars/<char_id>.json),用到哪个载哪个
@lru_cache(maxsize=64)
def _plan(char_id: str) -> dict | None:
    path = _DATA / "chars" / f"{char_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# 记得 close() 里 _plan.cache_clear()
```

建议用 pydantic 模型解 JSON:字段损坏时 `ValidationError` 本身就是 `ValueError`,正好符合契约的报错语义。

### 评级素材

`GradeSpec(id="ACE", color=(240, 136, 62), icon=None)`:

- `icon=None` 完全够用:渲染端画「主色圆底 + 评级文字」的自动徽章,一张图不做也能跑通全部卡片。文字按实际宽度自动缩小,长 id 不会溢出,但建议 ≤2 字符。
- 想用自己的图:方形透明底 PNG,建议 ≥92px(最大渲染 92,其余尺寸同图缩放),放包内 `assets/`,`icon=Path(__file__).parent / "assets" / "rank_ACE.png"`。**素材必须随包分发**,不要引用 NTEUID 其它目录的贴图。
- `color` 同时是排行里分数文字的颜色,不控制角色卡词条高亮;词条颜色由可选的 `highlight_color()` 决定。

## 参考实现

- `providers/roll_value.py` — 内置词条折算:单词条得分 = 词条数值 ÷ 标准词条价值,按角色方案计核心主词条 + 推荐副词条。"写法二"数据组织的完整参考。它读的 `resource/scoring/*.json` 是私有数据,别的评分包不要依赖。
- 想写伤害期望类算法,可以直接复用 `NTEUID/utils/damage`(乘区公式 `formula.py`、面板解析 `profiles.py`):对词条做数值微扰算边际伤害增益,增益即分数。

## 底层机制(想深究再看)

- **加载**:首次用到评分时扫描 `scorers/`,每个子目录按 `<name>/__init__.py` 导入,导入即注册;`_` 和 `.` 开头的目录跳过。某个包加载失败只 warning 跳过,不影响其它包和插件本体;`scorer_id` 重复注册直接报错。
- **切换**:配置变更后下一次出图生效,流程是 `新.prepare() → 激活 → 旧.close()`,有锁防并发,prepare 失败保持旧算法。
- **更新生效范围**:数据文件和评级词表/素材在**重新激活时**重载(`ntescorer更新` 后切走再切回即可);但 Python **代码**更新必须重启 Bot,模块不会热重载。通过 `ntescorer增加` 装新包后也需要重启才会被发现。
- **榜单隔离**:每条评分记录都带产出它的 `scorer_id`,排行 / 最强只在同算法的记录之间比较。不同算法的分数量纲不同,永远不会同榜混排;切包后旧分数自然退出榜单,重新刷新面板即按新算法入榜。另外空串 `grade` 被系统保留表示"不可评分",不要当合法评级用。
