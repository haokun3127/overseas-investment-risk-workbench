"""Fixed knowledge corpus shared by the retrieval golden and hit-window tests."""
from app.ingest import insert_document

LONG_BODY = (
    "Peraturan Menteri Ketenagakerjaan tentang tata cara penggunaan tenaga kerja asing. " * 20
    + "Bagian umum mengatur kewajiban administrasi perusahaan. " * 30
    + "Setiap pemberi kerja wajib memiliki RPTKA sebelum mempekerjakan TKA. "
    + "Pengesahan RPTKA diterbitkan oleh Kemnaker melalui sistem daring. " * 3
)

DOCUMENTS = [
    {
        "title": "Permenaker Nomor 8 Tahun 2021",
        "body": LONG_BODY,
        "source": "Kemnaker",
        "date": "2021-03-01",
        "zh_summary": "印尼劳工部关于外籍劳工使用程序的部长条例，规定RPTKA审批与雇主义务。",
        "zh_keywords": "外籍劳工、RPTKA、劳工部、工作许可",
    },
    {
        "title": "OSS 门户首页",
        "body": "Visit OSS. Perizinan Berusaha Berbasis Risiko. Powered by sagara 2022. Hubungi kami. Login.",
        "source": "oss.go.id",
        "date": "2022-01-01",
        "zh_summary": "",
        "zh_keywords": "",
    },
    {
        "title": "印尼外籍劳工工作许可办理指南",
        "body": "外籍劳工在印尼工作需先取得工作许可。雇主应提交用工计划，并缴纳技能发展基金。许可有效期一般为一年。",
        "source": "商务参赞处",
        "date": "2024-05-10",
        "zh_summary": "",
        "zh_keywords": "",
    },
    {
        "title": "Peraturan Pemerintah Nomor 5 Tahun 2021",
        "body": "Penyelenggaraan perizinan berusaha berbasis risiko melalui sistem OSS untuk seluruh sektor usaha.",
        "source": "JDIH",
        "date": "2021-02-02",
        "zh_summary": "印尼政府关于基于风险的营业许可条例，适用于全部行业。",
        "zh_keywords": "营业许可、风险分级、OSS",
    },
    {
        "title": "海关进口清关注意事项",
        "body": "进口货物需申报海关并缴纳关税。部分商品受进口限制，需提前取得进口批准。",
        "source": "海关",
        "date": "2023-08-08",
        "zh_summary": "",
        "zh_keywords": "",
    },
]

QUERIES = ["外籍劳工", "劳工许可", "进口清关", "perizinan berusaha", "营业许可"]


def build_corpus(store):
    ids = []
    for item in DOCUMENTS:
        record = {key: item[key] for key in ("title", "body", "source", "date")}
        doc_id, _ = insert_document(store, record, "knowledge", True)
        with store.db() as db:
            db.execute(
                "UPDATE documents SET zh_summary=?,zh_keywords=?,zh_state=? WHERE id=?",
                (item["zh_summary"], item["zh_keywords"], "done" if item["zh_summary"] else "", doc_id),
            )
        ids.append(doc_id)
    return ids
