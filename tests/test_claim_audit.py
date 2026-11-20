#!/usr/bin/env python3
"""1.8.0 引用核验回归：错误金额/对象错配/仅非官方/失效记录必须判未通过。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from claim_audit import audit_answer  # noqa: E402

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def source(excerpt="补贴标准为每户10万元。申请条件为在本市注册满一年。", *, unofficial=False,
           citable=True, title="某补贴政策通知", url=""):
    return {
        "id": "1", "title": title, "url": url, "excerpt": excerpt,
        "segments": [{"text": excerpt}], "used": True,
        "citable": citable, "unofficial": unofficial,
    }


def statuses(result):
    return {item.get("status") for item in result["checks"]}


def main():
    good = audit_answer("补贴标准为每户10万元[1]。", [source()], {})
    check("正确金额通过", good["passed"] is True, str(good["checks"]))
    check("正确金额来源标记通过", good["claim_verified"]["1"] is True)

    wrong = audit_answer("补贴标准为每户20万元[1]。", [source()], {})
    check("错误金额不通过", wrong["passed"] is False)
    check("错误金额标 unverified_fact", "unverified_fact" in statuses(wrong), str(statuses(wrong)))
    check("错误金额来源标记不通过", wrong["claim_verified"]["1"] is False)

    official = source()
    external = source(unofficial=True)
    only_external = audit_answer("补贴标准为每户10万元[1]。", [external], {})
    check("仅非官方来源不通过", only_external["passed"] is False)
    check("仅非官方来源标 non_official_only", "non_official_only" in statuses(only_external))

    absent = audit_answer("该政策未规定申请条件[1]。", [official], {})
    check("缺席推断为待人工复核", absent["passed"] is True)
    check("缺席推断标 absence_claim", "absence_claim" in statuses(absent))
    check("缺席推断为软提醒", any(c.get("status") == "absence_claim" and c.get("severity") == "soft"
                          for c in absent["checks"]))

    stale_payload = {"selfCheck": {"answer_digest": "deadbeef", "no_gap": "通过"}}
    stale = audit_answer("补贴标准为每户10万元[1]。", [source()], stale_payload)
    check("答案摘要不一致判失效", stale["stale"] is True and stale["passed"] is False)
    check("失效记录来源不得标通过", stale["claim_verified"]["1"] is False)

    no_excerpt = audit_answer("补贴标准为每户10万元[1]。", [source(excerpt="")], {})
    check("无摘录是软提醒，不判未通过", no_excerpt["passed"] is True)
    check("无摘录来源仍标引用核验通过", no_excerpt["claim_verified"]["1"] is True)
    check("无摘录状态为 soft", any(c.get("status") == "no_excerpt" and c.get("severity") == "soft"
                                  for c in no_excerpt["checks"]))

    soft_payload = {"verification": {"checks": [
        {"status": "semantic_review", "sentence": "补贴标准为每户10万元[1]", "note": "需人工复核"}
    ]}}
    soft = audit_answer("补贴标准为每户10万元[1]。", [source()], soft_payload)
    check("semantic_review 不改变已核验", soft["passed"] is True)
    check("semantic_review 来源仍标通过", soft["claim_verified"]["1"] is True)

    hard_payload = {"verification": {"checks": [
        {"status": "jev_not_supported", "sentence": "补贴标准为每户10万元[1]", "note": "原文不支持"}
    ]}}
    hard = audit_answer("补贴标准为每户10万元[1]。", [source()], hard_payload)
    check("jev_not_supported 判未通过", hard["passed"] is False and hard["claim_verified"]["1"] is False)

    # 2026-11-20 审核复现用例（阻断 1-6）
    mismatch = audit_answer("生育津贴按158天计发[1]。", [source(excerpt="女职工产假为158天。")], {})
    check("对象错配为待人工复核", mismatch["passed"] is True)
    check("对象错配标 amount_mismatch", "amount_mismatch" in statuses(mismatch))

    amount = audit_answer("生育津贴标准为每月300元[1]。", [source(excerpt="高温津贴标准为每月300元。")], {})
    check("金额主体错配为待人工复核", amount["passed"] is True)

    old_std = audit_answer("车辆检验按GB21861执行[1]。", [source(excerpt="现行标准为GB 38900。")], {})
    check("旧标准判未通过", old_std["passed"] is False and "outdated_standard" in statuses(old_std))

    no_cite = audit_answer("每月最高1500元[1]。另外，还需提供户口本。",
                           [source(excerpt="每月最高1500元。")], {})
    check("补充要件句无角标判未通过", no_cite["passed"] is False
          and "core_without_citation" in statuses(no_cite))

    no_need = audit_answer("该业务无需提供户口本[1]。", [source(excerpt="申请材料包括身份证、户口本。")], {})
    check("无需/不需要判缺席推断", no_need["passed"] is True and "absence_claim" in statuses(no_need))

    cross = audit_answer("该政策未规定申请材料[1]。", [source(excerpt="本通知不适用于外地户籍人员。")], {})
    check("跨主题缺席推断仍提示", cross["passed"] is True and "absence_claim" in statuses(cross))

    cn_num = audit_answer("每月最高可提取1500元[1]。", [source(excerpt="每月最高可提取一千五百元。")], {})
    check("中文数字可匹配", cn_num["passed"] is True)

    wan = audit_answer("每月最高可提取1.5万元[1]。", [source(excerpt="每月最高可提取15000元。")], {})
    check("万元换算可匹配", wan["passed"] is True)

    pct = audit_answer("缴存比例为50%[1]。", [source(excerpt="缴存比例为百分之五十。")], {})
    check("中文百分比可匹配", pct["passed"] is True)

    local = audit_answer("北京户籍家庭可申请租房提取[1]。",
                         [source(excerpt="本市户籍家庭可申请租房提取。", title="北京市租房提取办法")], {})
    check("本市自指不误判地域", local["passed"] is True)

    cross_city = audit_answer("上海户籍家庭可申请租房提取[1]。",
                              [source(excerpt="本市户籍家庭可申请租房提取。", title="北京市租房提取办法")], {})
    check("本市不跨城放行", cross_city["passed"] is False
          and "unverified_fact" in statuses(cross_city))

    no_need_rewrite = audit_answer("该业务无需提供户口本[1]。", [source(excerpt="申请无需提供户口本。")], {})
    check("缺席改写主语可通过", no_need_rewrite["passed"] is True)

    no_need_appointment = audit_answer("该业务无需预约[1]。", [source(excerpt="申请人无需预约，可直接办理。")], {})
    check("缺席同义词可通过", no_need_appointment["passed"] is True)

    no_requirement = audit_answer("该业务不需要社保[1]。", [source(excerpt="本通知不要求社保。")], {})
    check("不要求/不需要等价", no_requirement["passed"] is True)

    elder = audit_answer("高龄津贴每月300元[1]。", [source(excerpt="80周岁以上老年人每月发放津贴300元。")], {})
    check("津贴简称不误判错配", elder["passed"] is True)

    qualitative = audit_answer("缴费比例为单位和个人共同承担[1]。",
                               [source(excerpt="单位和个人缴费比例分别为16%和8%。")], {})
    check("定性比例不判关键数字缺失", qualitative["passed"] is True)

    std_year = audit_answer("按GB38900-2020执行[1]。", [source(excerpt="现行标准为GB 38900。")], {})
    check("标准号年份可省略", std_year["passed"] is True)

    policy_sentence = audit_answer("申请人应提交身份证。", [source(excerpt="申请人应提交身份证原件。")], {})
    check("政策要求句无角标判未通过", policy_sentence["passed"] is False
          and "core_without_citation" in statuses(policy_sentence))

    email_sentence = audit_answer("您好：\n同时，需提供您的身份证复印件。",
                                  [source(excerpt="申请人应提交身份证复印件。")], {})
    check("邮件请求句不判无角标", email_sentence["passed"] is True)

    # 2026-11-20 复审二：同段无关否定不得为相反断言作证
    contrast = audit_answer("该业务无需提供身份证[1]。",
                            [source(excerpt="申请无需提供户口本，但需提供身份证。")], {})
    check("同段无关否定仍提示", contrast["passed"] is True
          and "absence_claim" in statuses(contrast))

    contrast_ok = audit_answer("该业务无需提供户口本[1]。",
                               [source(excerpt="申请无需提供户口本，但需提供身份证。")], {})
    check("同段否定本身仍可通过", contrast_ok["passed"] is True)

    local_url = audit_answer("北京户籍家庭可申请[1]。",
                             [source(excerpt="本市户籍家庭可申请。", title="关于租房提取的通知",
                                     url="https://www.beijing.gov.cn/zfxxgk/1.html")], {})
    check("URL 拼音城市参与判定", local_url["passed"] is True)

    delegated = audit_answer("补贴标准为当地政府确定[1]。",
                             [source(excerpt="补贴标准为3万元，具体由当地政府确定。")], {})
    check("标准推给当地政府判关键数字缺失", delegated["passed"] is False
          and "missing_key_figure" in statuses(delegated))

    # 2026-11-20 复审三：可提供/建议提供/相应 不是强制要求
    optional = audit_answer("申请无需提供户口本[1]。",
                            [source(excerpt="申请人可提供户口本复印件作为辅助材料。")], {})
    check("可提供不算强制要求", optional["passed"] is True)

    advised = audit_answer("申请无需提供社保记录[1]。",
                           [source(excerpt="建议提供社保记录以便核对。")], {})
    check("建议提供不算强制要求", advised["passed"] is True)

    relative = audit_answer("申请无需居住证[1]。",
                            [source(excerpt="持居住证相应人员可申请租房补贴。")], {})
    check("相应不是应提供", relative["passed"] is True)

    old_word = audit_answer("按原标准，女职工产假为98天[1]。", [source(excerpt="女职工产假为98天。")], {})
    check("原标准历史口径不判废止", old_word["passed"] is True)

    summary = audit_answer("所有申请材料均可线上提交[1]。", [source(excerpt="申请材料可线上提交。")], {})
    check("总结句所有不判措辞风险", summary["passed"] is True)

    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
