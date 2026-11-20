#!/usr/bin/env python3
"""引用核验：把“答案里的每个结论”与“它引用的原文摘录”做可复现比对。

只做能解释、能复现的检查，不冒充语义模型：
- 数字/单位、书名号/引号短语必须在被引摘录中出现；
- 明确否定（未规定/不适用）、推算（约为/折合）、废止/失效、强措辞必须有原文依据；
- 全部依据为非官方来源时标 non_official_only；
- 显式 verification.checks / gaps / selfCheck 原样纳入；
- answer/evidence digest 不一致时整份核验记录失效，禁止沿用旧绿标。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

CITATION_RE = re.compile(r"\[(\d+)\]")
SENTENCE_RE = re.compile(r"[^。！？；\n]+[。！？；]?")
NUM_UNITS = r"(万元|亿元|元|%|％|个工作日|工作日|周岁|岁|个月|月|天|日|年|套|人|次|倍|公里|千米|平方米|㎡)"
NUMBER_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*" + NUM_UNITS)
CN_NUMBER_RE = re.compile(r"([零〇一二两三四五六七八九十百千万亿]+)\s*" + NUM_UNITS)
CN_PERCENT_RE = re.compile(r"百分之([零〇一二两三四五六七八九十百千]+)")
STANDARD_RE = re.compile(r"(GB(?:/T)?\s*\d+(?:\.\d+)?(?:\s*[-—]\s*\d{4})?)", re.I)
PHRASE_RE = re.compile(r"《([^》]{2,40})》")

ABSENCE_WORDS = (
    "未规定", "没有规定", "未明确", "不适用", "不包含", "未提及", "无此规定", "不属于", "不涉及",
    "无需", "无须", "不需要", "不必", "免于", "不要求", "未要求", "不须", "不用",
)
DERIVED_WORDS = ("推算", "据此计算", "折合", "相当于", "约为", "大约", "预计")
REPEAL_WORDS = ("废止", "失效", "已被替代", "被替代", "不再执行")
# “所有/全部”是总结句常态，不再作为绝对化措辞；只保留真正的全称/强制表述。
STRONG_WORDS = ("必须", "一律", "绝对")
REGIONS = (
    "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏",
    "新疆", "香港", "澳门", "台湾", "广州", "深圳", "佛山", "东莞", "珠海", "杭州",
    "南京", "苏州", "成都", "武汉", "西安", "郑州", "济南", "青岛", "厦门", "宁波",
)

# 政府站点域名常用拼音：用于“本市”自指与答案城市的一致性判定（标题/机构缺失时兜底）。
REGION_PINYIN = {
    "beijing": "北京", "shanghai": "上海", "tianjin": "天津", "chongqing": "重庆",
    "hebei": "河北", "shanxi": "山西", "liaoning": "辽宁", "jilin": "吉林",
    "heilongjiang": "黑龙江", "jiangsu": "江苏", "zhejiang": "浙江", "anhui": "安徽",
    "fujian": "福建", "jiangxi": "江西", "shandong": "山东", "henan": "河南",
    "hubei": "湖北", "hunan": "湖南", "guangdong": "广东", "hainan": "海南",
    "sichuan": "四川", "guizhou": "贵州", "yunnan": "云南", "shaanxi": "陕西",
    "gansu": "甘肃", "qinghai": "青海", "neimenggu": "内蒙古", "guangxi": "广西",
    "xizang": "西藏", "ningxia": "宁夏", "xinjiang": "新疆",
    "guangzhou": "广州", "shenzhen": "深圳", "foshan": "佛山", "dongguan": "东莞",
    "zhuhai": "珠海", "hangzhou": "杭州", "nanjing": "南京", "suzhou": "苏州",
    "chengdu": "成都", "wuhan": "武汉", "xian": "西安", "zhengzhou": "郑州",
    "jinan": "济南", "qingdao": "青岛", "xiamen": "厦门", "ningbo": "宁波",
}


def _url_region_hints(url: str) -> str:
    host = re.sub(r"^[a-z]+://", "", str(url or "")).split("/")[0].lower()
    tokens = re.split(r"[.\-]", host)
    return " ".join(REGION_PINYIN[token] for token in tokens if token in REGION_PINYIN)


STATUS_LABELS = {
    "ok": "通过",
    "uncitable": "不可引用材料",
    "no_excerpt": "无摘录",
    "non_official_only": "仅非官方来源",
    "unverified_fact": "未定位事实",
    "amount_mismatch": "金额/对象错配",
    "core_without_citation": "核心结论无角标",
    "semantic_review": "语义复核",
    "jev_abstain": "语义核验弃答",
    "jev_not_supported": "原文不支持",
    "absence_claim": "缺席推断",
    "derived": "推算值",
    "wording_risk": "措辞口径",
    "outdated_standard": "旧标准",
    "missing_key_figure": "关键数字缺失",
    "repeal_claim_unsupported": "废止/旧数无依据",
    "stale_verification": "核验记录已失效",
    "explicit_fail": "上游核验未通过",
}

GAP_LABELS = {
    "fact_unverified": "事实点未定位",
    "judge_error": "判级接口失败",
    "no_usable_evidence": "没有可用依据",
    "current_applicability": "当前适用性待核",
    "non_official_only": "核心结论仅非官方来源",
    "currentness_gap": "有更新的官方材料未进入答案",
    "stale_primary": "最高等级依据偏旧",
    "conflict_unresolved": "官方口径冲突",
}

PASS_STATUSES = {"ok", "verified", "jev_supported"}

# 两档口径（脚本管字面、模型管语义）：
# 可脚本复现的字面问题判硬错误；语义类判断（缺席、金额对象归属、措辞）降为人工复核。
SOFT_STATUSES = {
    "semantic_review", "jev_abstain", "derived", "no_excerpt",
    "absence_claim", "amount_mismatch", "wording_risk",
}
HARD_STATUSES = {
    "unverified_fact", "core_without_citation",
    "non_official_only", "jev_not_supported",
    "outdated_standard", "missing_key_figure",
    "repeal_claim_unsupported", "judge_error", "stale_verification",
    "uncitable", "explicit_fail",
}
HARD_GAP_TYPES = {"judge_error", "no_usable_evidence", "fact_unverified"}


def _norm(text: Any) -> str:
    value = str(text or "")
    value = value.replace("％", "%").replace("㎡", "平方米")
    return re.sub(r"[^0-9a-zA-Z一-鿿%]+", "", value).lower()


def _bigrams(text: str) -> Set[str]:
    return {text[i:i + 2] for i in range(max(0, len(text) - 1))}


def _overlap_ratio(sentence: str, excerpt: str) -> float:
    left = _bigrams(_norm(sentence))
    right = _bigrams(_norm(excerpt))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def _source_text(source: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(source.get("title") or ""),
        str(source.get("issuer") or ""),
        str(source.get("doc_number") or ""),
        str(source.get("date") or ""),
        str(source.get("excerpt") or ""),
    ]
    for segment in source.get("segments") or []:
        if isinstance(segment, dict):
            parts.append(str(segment.get("text") or ""))
    return "\n".join(part for part in parts if part.strip())


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
CN_BIG = {"万": 10 ** 4, "亿": 10 ** 8}


def _cn_to_number(text: str) -> Optional[float]:
    """中文数字转数值（支持百/千/万/亿），无法解析返回 None。"""
    total = 0.0
    section = 0.0
    number = 0.0
    seen = False
    for char in text:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
            seen = True
        elif char in CN_UNITS:
            section += (number or 1) * CN_UNITS[char]
            number = 0.0
            seen = True
        elif char in CN_BIG:
            section = (section + number) * CN_BIG[char]
            total += section
            section = 0.0
            number = 0.0
            seen = True
        else:
            return None
    if not seen:
        return None
    return total + section + number


def _unit_value(unit: str) -> Tuple[str, float]:
    """单位归一：返回（量纲, 倍率），把万元/亿元折成元、％折成百分比。"""
    mapping = {
        "万元": ("元", 10000.0), "亿元": ("元", 100000000.0), "元": ("元", 1.0),
        "%": ("percent", 1.0), "％": ("percent", 1.0),
        "周岁": ("岁", 1.0), "岁": ("岁", 1.0),
        "个月": ("月", 1.0), "月": ("月", 1.0),
        "天": ("天", 1.0), "日": ("天", 1.0),
        "个工作日": ("工作日", 1.0), "工作日": ("工作日", 1.0),
        "年": ("年", 1.0), "套": ("套", 1.0), "人": ("人", 1.0),
        "次": ("次", 1.0), "倍": ("倍", 1.0),
        "公里": ("公里", 1.0), "千米": ("公里", 1.0),
        "平方米": ("平方米", 1.0), "㎡": ("平方米", 1.0),
    }
    return mapping.get(unit, ("其他", 1.0))


def _number_items(text: str) -> List[Dict[str, Any]]:
    """抽取数值并归一：阿拉伯数字、中文数字、百分之X、万元/亿元换算。"""
    items: List[Dict[str, Any]] = []
    for match in NUMBER_UNIT_RE.finditer(text or ""):
        raw = match.group(1) + match.group(2)
        dim, factor = _unit_value(match.group(2))
        try:
            value = float(match.group(1)) * factor
        except ValueError:
            continue
        items.append({"value": value, "dim": dim, "raw": raw.replace("％", "%"),
                      "start": match.start(), "end": match.end()})
    for match in CN_PERCENT_RE.finditer(text or ""):
        value = _cn_to_number(match.group(1))
        if value is None:
            continue
        items.append({"value": value, "dim": "percent", "raw": match.group(0),
                      "start": match.start(), "end": match.end()})
    arabic_spans = [(item["start"], item["end"]) for item in items]
    for match in CN_NUMBER_RE.finditer(text or ""):
        if CN_PERCENT_RE.search(text[max(0, match.start() - 3):match.start()]):
            continue
        # “1.5万元”里的“万元”不是中文数字，跳过与阿拉伯数字重叠的匹配。
        if any(match.start() < end and start < match.end() for start, end in arabic_spans):
            continue
        if not any(char in CN_DIGITS for char in match.group(1)):
            continue
        value = _cn_to_number(match.group(1))
        if value is None:
            continue
        dim, factor = _unit_value(match.group(2))
        items.append({"value": value * factor, "dim": dim, "raw": match.group(0),
                      "start": match.start(), "end": match.end()})
    items.sort(key=lambda item: item["start"])
    return items


def _numbers(text: str) -> List[str]:
    return [item["raw"] for item in _number_items(text)]


def _same_value(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if left["dim"] != right["dim"]:
        return False
    tolerance = max(0.01, abs(left["value"]) * 0.005)
    return abs(left["value"] - right["value"]) <= tolerance


# 只对“金额/期限类对象”做绑定检查：主语必须落在这些常见名词上，避免把介词短语当对象。
SUBJECT_SUFFIXES = (
    "津贴", "补贴", "工资", "保险", "保险金", "公积金", "产假", "年休假", "休假",
    "标准", "金额", "比例", "期限", "天数", "年限", "社保", "养老金", "租金",
    "额度", "费用", "奖励", "补助", "待遇", "缴费", "基数", "税款", "税额",
    "利率", "费率", "赔偿金", "抚恤金", "补助金",
)

_SUBJECT_TRIM = (
    "为", "是", "按", "达", "至", "到", "最高", "最低", "上限", "下限", "不超过", "每月", "每年",
    "每人", "每户", "累计", "合计", "共计", "约", "可", "能", "提取", "领取", "发放", "缴纳", "缴费",
    "补贴", "标准", "金额", "比例", "不得", "享受", "应", "需", "须",
)


def _subject_before(text: str, end: int) -> str:
    """取数值前的对象短语（如“生育津贴”“高温津贴”），用于对象错配检查。"""
    prefix = (text or "")[:end]
    prefix = re.sub(r"[，。；：、（）()\s]+$", "", prefix)
    changed = True
    while changed:
        changed = False
        for word in _SUBJECT_TRIM:
            if prefix.endswith(word):
                prefix = prefix[: -len(word)]
                changed = True
                break
    match = re.search(r"([一-鿿]{2,6})$", prefix)
    subject = match.group(1) if match else ""
    # 去掉主语里的时间/动词前缀（“每月发放津贴”→“津贴”），保留真正的限定词。
    changed = True
    while changed and subject:
        changed = False
        for word in ("每月", "每年", "每人", "每户", "发放", "领取", "缴纳", "连续", "累计", "标准"):
            if subject.startswith(word) and len(subject) > len(word):
                subject = subject[len(word):]
                changed = True
                break
    return subject


def _suffix_of(subject: str) -> str:
    return next((suffix for suffix in SUBJECT_SUFFIXES if subject.endswith(suffix)), "")


def _subject_compatible(left: str, right: str) -> bool:
    """同口径判定：词尾（津贴/补贴/工资…）一致，且限定前缀不冲突。

    “高龄津贴”对“津贴”视为同口径（简称）；“生育津贴”对“高温津贴”判冲突。
    """
    if _norm(left) in _norm(right) or _norm(right) in _norm(left):
        return True
    left_suffix, right_suffix = _suffix_of(left), _suffix_of(right)
    if not left_suffix or not right_suffix or left_suffix != right_suffix:
        return False
    left_prefix = left[: -len(left_suffix)]
    right_prefix = right[: -len(right_suffix)]
    if not left_prefix or not right_prefix:
        return True
    return left_prefix in right_prefix or right_prefix in left_prefix


def _strip_standard_year(code: str) -> str:
    return re.sub(r"[-—]\s*\d{4}$", "", code)


def _subject_after(text: str, start: int) -> str:
    """取缺席词之后的对象短语（如“无需提供户口本”里的“户口本”）。"""
    rest = re.sub(r"^[，。；：、（）()\s]*(提供|提交|出具|附送|报送|上传|携带|包含|包括|涉及|适用|属于)?",
                  "", (text or "")[start:])
    match = re.match(r"([一-鿿]{2,6})", rest)
    return match.group(1) if match else ""


CORE_MARKERS = (
    "标准", "金额", "比例", "期限", "条件", "材料", "办理", "补贴", "缴费", "基数",
    "天数", "年限", "待遇", "资格", "申请", "依据", "应当", "不得", "享受", "提供",
)
CORE_SKIP_PREFIXES = (
    "您好", "尊敬的", "此致", "申请人：", "本人", "我", "现申请", "拟于", "（一）申请事项",
    "主题：", "标题：",
)
# 只抓“补充要件句”这类最常见的无角标实质结论；不搞逐句全量判定，避免误伤上下文句。
CORE_CLAIM_RE = re.compile(
    r"^(另外|此外|同时|另需|还需|还须|并需)[^。]{0,20}(需|须|应)[^。]{0,10}(提供|提交|出具|材料|证明)"
)
# “对外陈述的政策要求”句式（如“申请人应提交身份证”）；第二人称的邮件请求句由调用方排除。
CORE_POLICY_RE = re.compile(
    r"^(申请人|职工|企业|单位|个人|参保人|群众)[^。]{0,25}(应|须|应当|需|应提供)[^。]{0,12}"
    r"(提交|提供|准备|携带|办理|申请|材料|证明)"
)


def _is_core_claim(sentence: str, letter_like: bool = False) -> bool:
    """判断一句未挂角标的句子是否属于需要依据的“核心结论”。"""
    raw = (sentence or "").lstrip()
    if raw.startswith("#") or raw.startswith("|"):
        return False
    text = CITATION_RE.sub("", sentence or "").strip()
    if text.startswith(CORE_SKIP_PREFIXES):
        return False
    if re.match(r"^主题[：:]|^标题[：:]", text):
        return False
    # 对收件人的请求（“需提供您的…”）不是政策结论；邮件/通知成品不做逐句角标判定。
    if letter_like or "您" in text or "你" in text:
        return False
    return bool(CORE_CLAIM_RE.search(text) or CORE_POLICY_RE.search(text))


def _phrases(text: str) -> List[str]:
    result = []
    for match in PHRASE_RE.finditer(text or ""):
        value = next((group for group in match.groups() if group), "")
        if value:
            result.append(value.strip())
    return result


CLAUSE_SPLIT_RE = re.compile(r"[，。；、\n]|但是|但|然而")
# 强制要求：强制词 + 4 字内的动作词。可提供/建议提供/相应材料等可选或非动作写法不算要求。
REQUIREMENT_RE = re.compile(
    r"(必须|需|须|应当|应)[^，。；、]{0,4}(提供|提交|出具|报送|准备|携带|包括|要求|办理|申请)"
)
OPTIONAL_WORDS = ("可提供", "可以", "建议", "宜", "自愿", "如需", "如需提供", "相应")


def _clauses(text: str) -> List[str]:
    """按逗号/句号/顿号与转折词切分小句；“但需提供…”必须与前面的“无需…”分开判。"""
    return [part.strip() for part in CLAUSE_SPLIT_RE.split(text or "") if part.strip()]


def _marker_kind(clause: str) -> str:
    if any(word in clause for word in ABSENCE_WORDS):
        return "absence"
    # “可提供/建议提供/相应材料”是可选或非强制表述：既不构成相反，也不能算无据。
    if any(word in clause for word in OPTIONAL_WORDS):
        return "optional"
    if REQUIREMENT_RE.search(clause):
        return "positive"
    return ""


def _sentences(answer: str) -> Iterable[Tuple[str, List[str]]]:
    for match in SENTENCE_RE.finditer(answer or ""):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        cids = []
        for cid in CITATION_RE.findall(sentence):
            if cid not in cids:
                cids.append(cid)
        yield sentence, cids


def _explicit_checks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        verification = {}
    checks = verification.get("checks") or payload.get("verificationChecks") or []
    return [dict(item) for item in checks if isinstance(item, dict)]


def _explicit_gaps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        verification = {}
    raw = verification.get("gaps") or payload.get("gaps") or []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def evidence_digest(sources: Sequence[Dict[str, Any]]) -> str:
    rows = []
    for source in sources:
        rows.append({
            "id": source.get("id"),
            "title": source.get("title"),
            "doc_number": source.get("doc_number"),
            "date": source.get("date"),
            "url": source.get("url"),
            "excerpt": source.get("excerpt"),
        })
    return _digest(rows)


def _sentence_check(sentence: str, cited: Sequence[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, str]]]:
    checks: List[Dict[str, str]] = []
    excerpts = "\n".join(_source_text(source) for source in cited)
    excerpt_norm = _norm(excerpts)

    def add(status: str, note: str) -> None:
        severity = "soft" if status in SOFT_STATUSES else "hard"
        checks.append({"status": status, "note": note, "severity": severity})

    if any(not (source.get("excerpt") or "").strip() for source in cited):
        add("no_excerpt", "被引材料没有可展示摘录")
        # 全部被引材料都没有摘录：只能提示人工复核，不能凭“找不到数字”判硬错误。
        if not any((source.get("excerpt") or "").strip() for source in cited):
            return True, checks
    if any(source.get("citable") is False for source in cited):
        add("uncitable", "被引材料为版本索引/无正文，不可引用")
    if cited and all(bool(source.get("unofficial")) for source in cited):
        add("non_official_only", "该结论只引用了非官方来源")

    excerpt_numbers: List[Dict[str, Any]] = []
    for source in cited:
        excerpt_numbers.extend(_number_items(_source_text(source)))

    missing_numbers: List[str] = []
    missing_subjects: List[str] = []
    for item in _number_items(sentence):
        matched = [candidate for candidate in excerpt_numbers if _same_value(item, candidate)]
        if not matched:
            missing_numbers.append(item["raw"])
            continue
        subject = _subject_before(sentence, item["start"])
        # 去掉“本市/本区…”等自指前缀后再看；过短（如“社保”被缩成两字）不做对象判定。
        subject = re.sub(r"^(本市|本区|本县|本地|我省|我市|我区)", "", subject)
        if len(subject) < 4 or not _suffix_of(subject):
            continue
        others = []
        for source in cited:
            text = _source_text(source)
            for candidate in _number_items(text):
                if _same_value(item, candidate):
                    others.append(_subject_before(text, candidate["start"]))
        others = [other for other in others if other and _suffix_of(other)]
        # 对象绑定：同一数值在原文中的对象必须与答案的对象同口径（词尾相同、限定前缀不冲突）。
        if others and not any(_subject_compatible(subject, other) for other in others):
            missing_subjects.append(subject)
    if missing_numbers:
        add("unverified_fact", "未定位：" + "、".join(missing_numbers[:6]))
    if missing_subjects:
        add("amount_mismatch", "金额/对象错配：" + "、".join(missing_subjects[:4]))

    # 旧标准：答案里的标准号（忽略年份）必须能在被引摘录中找到。
    standard_codes = [_strip_standard_year(re.sub(r"\s+", "", code).upper())
                      for code in STANDARD_RE.findall(sentence)]
    if standard_codes:
        excerpt_upper = re.sub(r"\s+", "", excerpts).upper()
        missing_codes = [code for code in standard_codes if code not in excerpt_upper]
        if missing_codes:
            add("outdated_standard", "标准号未在所引摘录中出现：" + "、".join(missing_codes[:4]))

    sentence_regions = [region for region in REGIONS if region in sentence]
    if sentence_regions and not any(region in excerpts for region in sentence_regions):
        # 市级文件常用“本市/本区/本地”自指：只有来源标题/机构/网址确实是该城市时才放行，
        # 防止把 A 城结论挂到 B 城材料上。
        self_refs = ("本市", "本区", "本县", "本地", "本省", "我市", "我区", "我县")
        meta = "\n".join(
            str(source.get(key) or "")
            for source in cited
            for key in ("title", "issuer", "url")
        ) + "\n" + "\n".join(_url_region_hints(source.get("url")) for source in cited)
        if not (any(word in excerpts for word in self_refs)
                and any(region in meta for region in sentence_regions)):
            add("unverified_fact", "未定位地域：" + "、".join(sentence_regions[:4]))

    missing_phrases = [item for item in _phrases(sentence)
                       if item and _norm(item) not in excerpt_norm]
    if missing_phrases:
        add("semantic_review", "未定位：" + "、".join(missing_phrases[:4]))

    absence_hits = [word for word in ABSENCE_WORDS if word in sentence]
    if absence_hits:
        supported = False
        contradicted = False
        for word in absence_hits:
            pos = sentence.find(word)
            # 优先取缺席词后的对象（“无需提供户口本”→“户口本”），取不到再退回主语。
            topic = _subject_after(sentence, pos + len(word)) or _subject_before(sentence, pos)
            if not topic:
                supported = any(item in excerpts for item in ABSENCE_WORDS)
                continue
            topic_norm = _norm(topic)
            if topic_norm not in excerpt_norm:
                continue
            # 按小句判定：“无需 X，但需 Y”里 X 与 Y 属不同小句，不能互相作证。
            for clause in _clauses(excerpts):
                if topic_norm not in _norm(clause):
                    continue
                kind = _marker_kind(clause)
                if kind in ("absence", "optional"):
                    supported = True
                    break
                if kind == "positive":
                    contradicted = True
                    break
            if supported or contradicted:
                break
        if contradicted:
            add("absence_claim", "答案的“无需/未规定”判断与原文要求相反")
        elif not supported:
            add("absence_claim", "答案作了“未规定/不适用/无需”判断，摘录中没有同主题的对应表述")

    if any(word in sentence for word in DERIVED_WORDS) and not _number_items(sentence):
        add("derived", "答案含推算表述，但没有可核对的数字")

    if any(word in sentence for word in REPEAL_WORDS) and not any(word in excerpts for word in REPEAL_WORDS):
        add("repeal_claim_unsupported", "答案称废止/失效/被替代，摘录无对应依据")

    strong = [word for word in STRONG_WORDS if word in sentence]
    if strong and not any(word in excerpts for word in ("必须", "一律", "均", "应当", "应")):
        add("wording_risk", "强措辞在摘录中没有对应表述")

    # 关键数字缺失：只抓“把关键数值推给另行公布/待定”的句子；定性说明（比例为…共同承担）不算。
    if not _number_items(sentence) and re.search(
        r"(标准|金额|比例|上限|基数|天数|期限)\s*(为|是)\s*"
        r"(另行|待定|按当地|由[^。]{0,8}确定|自行确定|另行公布|按现行|以[^。]{0,10}为准"
        r"|(当地|同级|本级|相关|上级)[^。]{0,8}(政府|部门)[^。]{0,4}确定)",
        sentence,
    ):
        add("missing_key_figure", "答案声称标准/金额但把关键数值推给另行公布")

    if not missing_numbers and not missing_phrases and not checks:
        if _overlap_ratio(sentence, excerpts) < 0.18:
            add("semantic_review", "答案句与被引摘录的字面重合度过低")

    return not any(item.get("severity") == "hard" for item in checks), checks


def audit_answer(answer: str, sources: Sequence[Dict[str, Any]],
                 payload: Dict[str, Any]) -> Dict[str, Any]:
    by_id = {str(source.get("id")): source for source in sources}
    used_sources = [source for source in sources if source.get("used", True)]
    claim_verified: Dict[str, Optional[bool]] = {str(source.get("id")): None for source in sources}
    soft_by_source: Dict[str, List[str]] = {str(source.get("id")): [] for source in sources}
    for source in used_sources:
        # no_excerpt 只作人工复核提醒，不改变“引用核验通过”；不可引用材料才是硬错误。
        claim_verified[str(source.get("id"))] = source.get("citable") is not False

    checks: List[Dict[str, Any]] = []
    failing_sources: Set[str] = set()
    # 邮件/通知型成品（含称呼或落款）不做逐句角标判定：其中的“需提供…”是对收件人的要求。
    letter_like = bool(re.search(r"(尊敬的|您好|此致|敬礼|申请人：|请示|兹申请)", answer or ""))
    for sentence, cids in _sentences(answer):
        if not cids:
            # 逐句核验：核心结论必须有角标；无角标的实质结论判硬错误。
            if used_sources and _is_core_claim(sentence, letter_like=letter_like):
                checks.append({
                    "status": "core_without_citation",
                    "severity": "hard",
                    "sentence": sentence[:180],
                    "note": "核心结论未挂来源角标",
                    "sources": [],
                })
            continue
        cited = [by_id[cid] for cid in cids if cid in by_id]
        if not cited:
            continue
        ok, sentence_checks = _sentence_check(sentence, cited)
        for check in sentence_checks:
            check["sentence"] = sentence[:180]
            check["sources"] = [str(source.get("id")) for source in cited]
            checks.append(check)
            if check.get("severity") == "soft":
                note = str(check.get("note") or check.get("status") or "")
                for source in cited:
                    soft_by_source.setdefault(str(source.get("id")), []).append(note)
        if not ok:
            failing_sources.update(str(source.get("id")) for source in cited)

    # 上游判级/核验调用失败：payload 显式报错时判硬错误（本 Skill 无内置判级，仅透传）。
    verification_error = ""
    if isinstance(payload.get("verification"), dict):
        verification_error = str(payload["verification"].get("error") or "").strip()
    if verification_error or payload.get("judge_error"):
        checks.append({
            "status": "judge_error", "severity": "hard", "sentence": "",
            "note": verification_error or "判级/核验调用失败",
            "sources": [str(source.get("id")) for source in used_sources],
        })
        failing_sources.update(str(source.get("id")) for source in used_sources)

    # 上游显式 checks：非通过状态同样使被引材料失效
    for item in _explicit_checks(payload):
        status = str(item.get("status") or "").strip()
        if not status or status in PASS_STATUSES:
            continue
        sentence = str(item.get("sentence") or "")
        cids = CITATION_RE.findall(sentence)
        row = {
            "status": status,
            "severity": "soft" if status in SOFT_STATUSES else "hard",
            "sentence": sentence[:180],
            "note": str(item.get("note") or item.get("why") or ""),
            "sources": cids,
        }
        checks.append(row)
        if row["severity"] == "hard":
            failing_sources.update(cids)
        else:
            for sid in cids:
                soft_by_source.setdefault(sid, []).append(row["note"] or status)

    # 上游显式 gaps
    gaps = _explicit_gaps(payload)
    self_check = payload.get("selfCheck") if isinstance(payload.get("selfCheck"), dict) else {}
    no_gap_value = str(self_check.get("no_gap") or "")
    if no_gap_value and not no_gap_value.startswith("通过"):
        gaps.append({"type": "fact_unverified", "severity": "blocking",
                     "why": f"自检 no_gap 未通过：{no_gap_value}"})
    hard_gap = any(
        gap.get("severity") == "blocking" or gap.get("type") in HARD_GAP_TYPES
        for gap in gaps
    )
    if hard_gap:
        for source in used_sources:
            failing_sources.add(str(source.get("id")))

    # 显式 引用核验通过=false
    for source in sources:
        if source.get("claim_verified") is False:
            failing_sources.add(str(source.get("id")))

    # digest 失效
    verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
    stale_reason = ""
    current_answer_digest = hashlib.sha256((answer or "").strip().encode("utf-8")).hexdigest()
    current_evidence_digest = evidence_digest(sources)
    for expected, current, label in (
        (verification.get("answer_digest"), current_answer_digest, "答案"),
        (verification.get("evidence_digest"), current_evidence_digest, "依据"),
        (self_check.get("answer_digest"), current_answer_digest, "答案"),
        (self_check.get("evidence_digest"), current_evidence_digest, "依据"),
    ):
        if expected and expected != current:
            stale_reason = f"{label}已变更，核验记录与当前内容不一致"
            break
    if payload.get("answer_stale"):
        stale_reason = stale_reason or "答案已变更，核验记录与当前答案不一致"
    if payload.get("evidence_stale"):
        stale_reason = stale_reason or "依据已变更，核验记录与当前材料不一致"
    if stale_reason:
        checks.append({"status": "stale_verification", "severity": "hard", "sentence": "",
                       "note": stale_reason,
                       "sources": [str(source.get("id")) for source in used_sources]})
        for source in used_sources:
            failing_sources.add(str(source.get("id")))

    for source in sources:
        sid = str(source.get("id"))
        if sid in failing_sources:
            claim_verified[sid] = False

    manual: List[str] = []
    seen: Set[str] = set()
    for check in checks:
        label = STATUS_LABELS.get(str(check.get("status")), str(check.get("status") or ""))
        note = str(check.get("note") or "").strip()
        prefix = "待人工复核：" if check.get("severity") == "soft" else ""
        text = prefix + f"{label}：{str(check.get('sentence') or '')[:90]}" + (f"（{note}）" if note else "")
        if text not in seen:
            seen.add(text)
            manual.append(text)
    for gap in gaps:
        label = GAP_LABELS.get(str(gap.get("type")), str(gap.get("type") or ""))
        why = str(gap.get("why") or gap.get("entity") or "").strip()
        text = f"缺口：{label}" + (f"（{why[:80]}）" if why else "")
        if text not in seen:
            seen.add(text)
            manual.append(text)

    blocking = hard_gap
    hard_checks = [item for item in checks if item.get("severity") == "hard"]
    soft_checks = [item for item in checks if item.get("severity") == "soft"]
    return {
        "claim_verified": claim_verified,
        "checks": checks,
        "hard_checks": hard_checks,
        "soft_checks": soft_checks,
        "soft_by_source": {key: value for key, value in soft_by_source.items() if value},
        "gaps": gaps,
        "failing_sources": sorted(failing_sources),
        "stale": bool(stale_reason),
        "stale_reason": stale_reason,
        "blocking": blocking,
        "answer_digest": current_answer_digest,
        "evidence_digest": current_evidence_digest,
        "manual_checks": manual[:40],
        "passed": not hard_checks and not blocking and not stale_reason,
    }
