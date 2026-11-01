"""Auditable date repair and evidence-preserving quarantine for stored documents.

Run from the repository root with the service stopped:
  python -m scripts.data_repair migrate
  python -m scripts.data_repair date-audit --out REPORT.json
  python -m scripts.data_repair date-apply --report REPORT.json [--exclude 1,2] [--include-review]
  python -m scripts.data_repair date-revert --log REPORT.json.applied.json
  python -m scripts.data_repair quarantine --documents 107,112,113 --expect-events 6,7,8,9,10 \
      --reason TEXT --evidence-dir DIR [--apply]
  python -m scripts.data_repair unquarantine --documents 107 --reason TEXT [--apply]
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
from pathlib import Path

from app import companies, websearch
from app.config import Settings
from app.store import Store, now

ARCHIVE_TITLE = re.compile(r"^［网页存档\s+(\d{4}-\d{2}-\d{2})］")
METHOD_SOURCE = {"rss": "feed", "api": "api"}


def connect(path, readonly=False):
    uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
    db = sqlite3.connect(uri, uri=True, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def backup_database(path, target):
    target = Path(target)
    if target.exists():
        raise ValueError(f"备份文件已存在，拒绝覆盖：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(path)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        source.close()
        copy.close()
    os.chmod(target, 0o600)
    return target


def document_fingerprint(db):
    """Stable across date-apply: cleared rows are fingerprinted by the value kept in date_legacy."""
    rows = db.execute(
        """SELECT id, CASE WHEN date_source='removed' AND date_legacy!='' THEN date_legacy ELSE date END original
           FROM documents ORDER BY id"""
    ).fetchall()
    payload = "\n".join(f"{row['id']}|{row['original']}" for row in rows).encode()
    return {
        "count": len(rows),
        "max_id": max((row["id"] for row in rows), default=0),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def first_text_date(title, body):
    match = re.search(
        r"\b(20\d{2}|19\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b",
        (title or "") + " " + (body or "")[:1000],
    )
    return match.group(0) if match else ""


def classify_documents(db):
    pages = {}
    for row in db.execute(
        "SELECT snapshot,date,fetched_at,archived_at,method,title FROM web_pages WHERE snapshot!='' ORDER BY id"
    ).fetchall():
        page = dict(row)
        page["date"] = websearch.normal_date(page["date"])
        if not page["archived_at"]:
            stamp = ARCHIVE_TITLE.match(page["title"] or "")
            page["archived_at"] = stamp.group(1) if stamp else ""
        pages[page["snapshot"]] = page
    result = []
    for row in db.execute(
        """SELECT id,title,body,date,created_at,file_path,date_source,date_legacy,archived_at,fetched_at
           FROM documents WHERE date_source='legacy' ORDER BY id"""
    ).fetchall():
        item = dict(row)
        page = pages.get(item["file_path"]) if item["file_path"] else None
        archive = ARCHIVE_TITLE.match(item["title"] or "")
        classification, action, details, source = "keep_legacy", "keep", "无法从数据判定来源，保留并标注来源未核实", ""
        if page and not page["date"]:
            classification, action, details = "web_no_page_date", "clear", "网站抓取未识别发布日期，资料日期为入库时补出"
        elif archive and item["date"] == archive.group(1) and not (page or {}).get("date"):
            classification, action, details = "archive_stamp_match", "clear", "资料日期等于网页存档快照日"
        elif page and item["date"] == page["date"]:
            classification, action, details = "web_page_date_match", "mark", "资料日期与网页发布日期一致"
            source = METHOD_SOURCE.get(page.get("method") or "", "page_meta")
        elif item["date"] and item["date"] == (item["created_at"] or "")[:10]:
            classification, action, details = "import_day_match", "clear", "资料日期等于入库当天（UTC）"
        elif item["date"] and item["date"] == first_text_date(item["title"], item["body"]):
            classification, action, details = "text_first_date_match", "review", "资料日期等于标题或正文开头第一个日期"
        item.pop("body")
        item.update(
            classification=classification,
            action=action,
            details=details,
            mark_source=source,
            web_date=(page or {}).get("date", ""),
            web_archived_at=(page or {}).get("archived_at", "") or (archive.group(1) if archive else ""),
            web_fetched_at=(page or {}).get("fetched_at", ""),
        )
        result.append(item)
    return result


def migrate(data_dir):
    store = Store(data_dir)
    companies.initialize(store)
    websearch.initialize(store)
    with store.db() as db:
        cleared = db.execute("DELETE FROM sessions").rowcount
        checks = {}
        for table, columns in {
            "documents": ["date_source", "date_legacy", "archived_at", "fetched_at", "quarantined_at", "quarantine_reason"],
            "sessions": ["active_company"],
            "audit": ["company_id"],
            "web_pages": ["archived_at"],
            "web_sources": ["target_company_id"],
        }.items():
            existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            checks[table] = all(column in existing for column in columns)
    report = {"migrated": checks, "sessions_cleared": cleared}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def date_audit(data_dir, output):
    path = Path(data_dir) / "risk.db"
    db = connect(path, readonly=True)
    try:
        report = {
            "created_at": now(),
            "database": str(path),
            "fingerprint": document_fingerprint(db),
            "items": classify_documents(db),
        }
    finally:
        db.close()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {}
    for item in report["items"]:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    print(json.dumps({"output": str(output), "counts": counts, "fingerprint": report["fingerprint"]}, ensure_ascii=False))
    return report


def date_apply(data_dir, report_path, exclude="", include_review=False, backup=None, log=None):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    excluded = {int(item) for item in str(exclude).split(",") if item.strip()}
    path = Path(data_dir) / "risk.db"
    log_path = Path(log or f"{report_path}.applied.json")
    db = connect(path)
    try:
        if document_fingerprint(db) != report["fingerprint"]:
            raise ValueError("数据库指纹与审计报告不一致，请重新运行 date-audit 后再审阅。")
        stamp = f"{now().replace(':', '')}-{secrets.token_hex(3)}"
        backup_path = backup_database(path, backup or f"{report_path}.before-apply-{stamp}.db")
        counts = {"cleared": 0, "marked": 0, "kept": 0, "unchanged": 0}
        changes = []
        db.execute("BEGIN IMMEDIATE")
        try:
            for item in report["items"]:
                action = item["action"]
                if action == "review" and include_review:
                    action = "clear"
                if item["id"] in excluded or action in ("keep", "review"):
                    counts["kept"] += 1
                    continue
                before = db.execute(
                    "SELECT date,date_source,date_legacy,archived_at,fetched_at FROM documents WHERE id=?",
                    (item["id"],),
                ).fetchone()
                if action == "clear":
                    changed = db.execute(
                        """UPDATE documents SET date_legacy=CASE WHEN date_legacy='' THEN date ELSE date_legacy END,
                           date='',date_source='removed' WHERE id=? AND date_source='legacy' AND date=?""",
                        (item["id"], item["date"]),
                    ).rowcount
                    key = "cleared"
                else:
                    changed = db.execute(
                        """UPDATE documents SET date_source=?,
                           archived_at=CASE WHEN archived_at='' THEN ? ELSE archived_at END,
                           fetched_at=CASE WHEN fetched_at='' THEN ? ELSE fetched_at END
                           WHERE id=? AND date_source='legacy' AND date=?""",
                        (item["mark_source"] or "page_meta", item.get("web_archived_at") or "",
                         item.get("web_fetched_at") or "", item["id"], item["date"]),
                    ).rowcount
                    key = "marked"
                if changed:
                    counts[key] += 1
                    changes.append({"id": item["id"], "action": action, "classification": item["classification"],
                                    "before": dict(before)})
                else:
                    counts["unchanged"] += 1
            db.execute(
                "INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,NULL)",
                ("dates_repaired", ", ".join(f"{k}={v}" for k, v in counts.items()), now()),
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    previous = json.loads(log_path.read_text(encoding="utf-8"))["changes"] if log_path.exists() else []
    log_path.write_text(json.dumps({"report": str(report_path), "backup": str(backup_path), "applied_at": now(),
                                    "changes": previous + changes}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": counts, "backup": str(backup_path), "log": str(log_path)}, ensure_ascii=False))
    return counts


def date_revert(data_dir, log_path):
    log = json.loads(Path(log_path).read_text(encoding="utf-8"))
    db = connect(Path(data_dir) / "risk.db")
    reverted = 0
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            for change in log["changes"]:
                before = change["before"]
                if change["action"] == "clear":
                    reverted += db.execute(
                        """UPDATE documents SET date=?,date_source=?,date_legacy=?
                           WHERE id=? AND date_source='removed' AND date='' AND quarantined_at IS NULL""",
                        (before["date"], before["date_source"], before["date_legacy"], change["id"]),
                    ).rowcount
                else:
                    reverted += db.execute(
                        """UPDATE documents SET date_source=?,archived_at=?,fetched_at=?
                           WHERE id=? AND date=? AND date_source NOT IN ('legacy','removed')""",
                        (before["date_source"], before["archived_at"], before["fetched_at"], change["id"], before["date"]),
                    ).rowcount
            db.execute(
                "INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,NULL)",
                ("dates_reverted", f"count={reverted}", now()),
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    print(json.dumps({"reverted": reverted}, ensure_ascii=False))
    return reverted


def parse_ids(value):
    ids = [int(item) for item in str(value).split(",") if item.strip()]
    if not ids:
        raise ValueError("请提供至少一个资料编号。")
    return list(dict.fromkeys(ids))


def collect_evidence(db, documents, output, uploads):
    marks = ",".join("?" * len(documents))
    evidence = {}
    queries = {
        "documents": f"SELECT * FROM documents WHERE id IN ({marks})",
        "chunks": f"SELECT * FROM chunks WHERE document_id IN ({marks})",
        "jobs": f"SELECT * FROM jobs WHERE document_id IN ({marks})",
        "analyses": f"SELECT * FROM analyses WHERE document_id IN ({marks})",
        "events": f"SELECT * FROM events WHERE analysis_id IN (SELECT id FROM analyses WHERE document_id IN ({marks}))",
        "review_history": f"""SELECT * FROM review_history WHERE event_id IN
            (SELECT id FROM events WHERE analysis_id IN (SELECT id FROM analyses WHERE document_id IN ({marks})))""",
        "web_pages": f"SELECT * FROM web_pages WHERE snapshot!='' AND snapshot IN (SELECT file_path FROM documents WHERE id IN ({marks}))",
    }
    for name, sql in queries.items():
        evidence[name] = [dict(row) for row in db.execute(sql, documents).fetchall()]
    (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"evidence.json": hashlib.sha256((output / "evidence.json").read_bytes()).hexdigest()}
    for item in evidence["documents"]:
        source = uploads / item["file_path"] if item.get("file_path") else None
        if source and source.is_file():
            target = output / "attachments" / source.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
            manifest[str(target.relative_to(output))] = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def quarantine(data_dir, document_ids, expected_events, reason, evidence_dir, apply=False):
    data_dir = Path(data_dir)
    ids = parse_ids(document_ids)
    expected = {int(item) for item in str(expected_events).split(",") if item.strip()}
    if not reason.strip():
        raise ValueError("请填写隔离原因。")
    Store(data_dir)
    marks = ",".join("?" * len(ids))
    db = connect(data_dir / "risk.db")
    try:
        documents = [dict(row) for row in db.execute(f"SELECT * FROM documents WHERE id IN ({marks}) ORDER BY id", ids)]
        events = {
            row["id"]
            for row in db.execute(
                f"SELECT e.id FROM events e JOIN analyses a ON a.id=e.analysis_id WHERE a.document_id IN ({marks})", ids
            )
        }
        if {item["id"] for item in documents} != set(ids):
            raise ValueError(f"目标资料不完整：期望 {sorted(ids)}，实际 {sorted(item['id'] for item in documents)}。")
        if events != expected:
            raise ValueError(f"关联事件不匹配：期望 {sorted(expected)}，实际 {sorted(events)}。未做任何修改。")
        pending = [item for item in documents if item["quarantined_at"] is None]
        plan = {
            "documents": [
                {
                    "id": item["id"], "title": item["title"], "url": item["url"], "date": item["date"],
                    "date_source": item["date_source"], "created_at": item["created_at"], "demo": item["demo"],
                    "company_id": item["company_id"], "characters": len(item["body"]),
                    "body_sha256": hashlib.sha256(item["body"].encode()).hexdigest(),
                    "already_quarantined": item["quarantined_at"] is not None,
                }
                for item in documents
            ],
            "events": sorted(events),
            "reason": reason,
            "apply": apply,
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        if not apply:
            return {"applied": False, "plan": plan}
        if not pending:
            print(json.dumps({"skipped": "全部资料已隔离，跳过"}, ensure_ascii=False))
            return {"applied": False, "skipped": True, "plan": plan}
        output = Path(evidence_dir).resolve()
        if output == data_dir.resolve() or data_dir.resolve() in output.parents:
            raise ValueError("证据目录必须位于数据目录之外。")
        if output.exists():
            raise ValueError("证据目录已存在，拒绝覆盖。")
        output.mkdir(mode=0o700, parents=True)
        db.execute("BEGIN IMMEDIATE")
        try:
            pending_ids = [item["id"] for item in pending]
            collect_evidence(db, pending_ids, output, data_dir / "uploads")
            backup_database(data_dir / "risk.db", output / "database-before.db")
            timestamp = now()
            pending_marks = ",".join("?" * len(pending_ids))
            db.execute(
                f"UPDATE jobs SET status='cancelled',finished_at=? WHERE document_id IN ({pending_marks}) AND status='queued'",
                (timestamp, *pending_ids),
            )
            for item in pending:
                own_events = sorted(
                    row["id"] for row in db.execute(
                        "SELECT e.id FROM events e JOIN analyses a ON a.id=e.analysis_id WHERE a.document_id=?",
                        (item["id"],),
                    )
                )
                db.execute(
                    """UPDATE documents SET quarantined_at=?,quarantine_reason=?,
                       date_legacy=CASE WHEN date_legacy='' THEN date ELSE date_legacy END,
                       date='',date_source='removed',allow_external=0
                       WHERE id=? AND quarantined_at IS NULL""",
                    (timestamp, reason, item["id"]),
                )
                db.execute(
                    "INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,?)",
                    (
                        "documents_quarantined",
                        f"document={item['id']}, events={','.join(map(str, own_events)) or '无'}, reason={reason}",
                        timestamp,
                        item["company_id"],
                    ),
                )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    result = {"applied": True, "quarantined": [item["id"] for item in pending], "evidence": str(output)}
    print(json.dumps(result, ensure_ascii=False))
    return result


def unquarantine(data_dir, document_ids, reason, apply=False):
    ids = parse_ids(document_ids)
    if not reason.strip():
        raise ValueError("请填写撤销隔离的原因。")
    if not apply:
        print(json.dumps({"documents": ids, "apply": False, "reason": reason}, ensure_ascii=False))
        return []
    marks = ",".join("?" * len(ids))
    db = connect(Path(data_dir) / "risk.db")
    changed = []
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            for row in db.execute(
                f"SELECT id,company_id FROM documents WHERE id IN ({marks}) AND quarantined_at IS NOT NULL", ids
            ).fetchall():
                db.execute("UPDATE documents SET quarantined_at=NULL,quarantine_reason='' WHERE id=?", (row["id"],))
                db.execute(
                    "INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,?)",
                    ("documents_unquarantined", f"document={row['id']}, reason={reason}", now(), row["company_id"]),
                )
                changed.append(row["id"])
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    print(json.dumps({"unquarantined": changed, "dates_restored": False}, ensure_ascii=False))
    return changed


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    audit = sub.add_parser("date-audit")
    audit.add_argument("--out", required=True)
    apply_dates = sub.add_parser("date-apply")
    apply_dates.add_argument("--report", required=True)
    apply_dates.add_argument("--exclude", default="")
    apply_dates.add_argument("--include-review", action="store_true")
    apply_dates.add_argument("--backup")
    apply_dates.add_argument("--log")
    revert = sub.add_parser("date-revert")
    revert.add_argument("--log", required=True)
    quarantine_parser = sub.add_parser("quarantine")
    quarantine_parser.add_argument("--documents", required=True)
    quarantine_parser.add_argument("--expect-events", required=True)
    quarantine_parser.add_argument("--reason", required=True)
    quarantine_parser.add_argument("--evidence-dir", required=True)
    quarantine_parser.add_argument("--apply", action="store_true")
    restore_parser = sub.add_parser("unquarantine")
    restore_parser.add_argument("--documents", required=True)
    restore_parser.add_argument("--reason", required=True)
    restore_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data_dir = Settings().data_dir
    if args.command == "migrate":
        migrate(data_dir)
    elif args.command == "date-audit":
        date_audit(data_dir, args.out)
    elif args.command == "date-apply":
        date_apply(data_dir, args.report, args.exclude, args.include_review, args.backup, args.log)
    elif args.command == "date-revert":
        date_revert(data_dir, args.log)
    elif args.command == "quarantine":
        quarantine(data_dir, args.documents, args.expect_events, args.reason, args.evidence_dir, args.apply)
    else:
        unquarantine(data_dir, args.documents, args.reason, args.apply)


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error))
