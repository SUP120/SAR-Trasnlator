from typing import Literal

from pydantic import BaseModel

from .analysis import AnalysisResult

Language = Literal["en", "hi"]


class Explanation(BaseModel):
    language: Language
    headline: str
    summary: str
    limitations: list[str]
    verification: str
    source: Literal["template"] = "template"


def dates_used(observations) -> str:
    return ", ".join(dict.fromkeys(scene.acquired_at.date().isoformat() for scene in observations))


def explain(result: AnalysisResult, language: Language) -> Explanation:
    before, after = dates_used(result.pre), dates_used(result.post)
    area = f"{result.stats.flood_ha:.2f}"
    if language == "hi":
        messages = {
            "possible_flooding": ("जल सतह बढ़ने के संकेत", f"लगभग {area} हेक्टेयर में जल सतह बढ़ने के संकेत मिले।"),
            "no_change_detected": ("जल सतह में बढ़ोतरी का संकेत नहीं मिला", "तुलना में तय मानदंडों के अनुसार जल सतह बढ़ने का संकेत नहीं मिला।"),
            "insufficient_data": ("तुलना के लिए पर्याप्त डेटा उपलब्ध नहीं है", "दोनों अवधियों में एक ही जगह के लिए मान्य डेटा उपलब्ध नहीं था।"),
        }
        headline, finding = messages[result.classification]
        if result.source == "synthetic":
            headline = "सिंथेटिक अभ्यास उदाहरण"
            finding = f"ये आँकड़े काल्पनिक डेटा से निकले हैं और किसी वास्तविक बाढ़ का प्रमाण नहीं हैं। {finding}"
        return Explanation(language=language, headline=headline,
                           summary=f"पहले के अवलोकन {before} और बाद के अवलोकन {after} के हैं। {finding}",
                           limitations=["रडार की छाया और चिकनी सतह पानी जैसी दिख सकती हैं। वनस्पति या इमारतों के बीच का पानी छूट सकता है।",
                                        "अवलोकन के समय बाढ़ अपने चरम पर हो, यह ज़रूरी नहीं है।"],
                           verification="आपातकाल या बीमा से जुड़े निर्णय लेने से पहले स्वतंत्र जानकारी से पुष्टि करें।")

    messages = {
        "possible_flooding": ("Possible surface-water expansion", f"The comparison suggests surface water expanded across about {area} hectares."),
        "no_change_detected": ("No qualifying surface-water expansion detected", "The comparison found no surface-water expansion that met the detection criteria."),
        "insufficient_data": ("Insufficient data for comparison", "No part of the study area had valid observations in both periods."),
    }
    headline, finding = messages[result.classification]
    if result.source == "synthetic":
        headline = "Synthetic practice example"
        finding = f"These figures come from invented inputs and provide no evidence of an actual flood. {finding}"
    return Explanation(language=language, headline=headline,
                       summary=f"Before observations were on {before}. After observations were on {after}. {finding}",
                       limitations=["Radar shadow and smooth surfaces can resemble water. Flooded vegetation and built-up areas may be missed.",
                                    "Satellite observation times can miss the peak of a flood."],
                       verification="Verify with independent evidence before emergency or insurance decisions.")
