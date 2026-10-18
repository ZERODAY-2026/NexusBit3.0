from lexlocal import knowledge
from lexlocal.analysis import translate

DEV = "".join(chr(0x0966 + d) for d in (2, 5))  # Devanagari "25"


def test_number_guard_handles_native_digits():
    assert translate.numbers(f"किराया {DEV},000 है") == {"25000"}
    assert translate.acceptable("Rent is Rs. 25,000 a month.", f"किराया {DEV},000 रुपये है।")
    assert not translate.acceptable("Rent is Rs. 25,000 a month.", "किराया 30,000 रुपये है।")  # invented number
    assert not translate.acceptable("Rent is due monthly.", "")
    assert not translate.acceptable("Rent is due monthly.", "This clause is unenforceable.")


def test_translate_batches_and_falls_back(fake_llm_cls):
    texts = ["Rent is Rs. 25,000 a month.", "Notice is one month."]
    llm = fake_llm_cls({"TranslationsOut": lambda u: {"translations": ["किराया 25,000 है।", "सूचना 99 दिन है।"]}})
    out = translate.translate_texts(llm, texts, "hi")
    assert out[0] == "किराया 25,000 है।" and out[1] is None  # second adds "99": rejected, English shown


def test_wrong_count_rejected(fake_llm_cls):
    llm = fake_llm_cls({"TranslationsOut": lambda u: {"translations": ["one"]}})
    assert translate.translate_texts(llm, ["a b c", "d e f"], "ta") == [None, None]


def test_fixed_disclaimers_exist_for_every_language():
    for lang in translate.LANGUAGES:
        d = knowledge.disclaimer(lang)
        assert d["disclaimer"] != knowledge.disclaimer("en")["disclaimer"]
        assert d["machine_translated"] and d["escalation"] and d["silent"]
