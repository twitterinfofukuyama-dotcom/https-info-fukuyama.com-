#!/usr/bin/env python3
"""PC用ファイル整理スクリプト（Windows / Mac / Linux 対応、Python 3.8+）

機能:
  - 拡張子ごとにカテゴリ別フォルダへ分類（任意で 年-月 サブフォルダも作成）
  - 重複ファイル（内容が同一）を「重複」フォルダへ退避（削除はしません）
  - 実行ログを保存し、--undo で元に戻せます
  - 既定は「ドライラン」（確認のみ）。実際に移動するには --run を付けます

使い方:
  python organize_files.py ~/Downloads                 # 確認のみ
  python organize_files.py ~/Downloads --run           # 実行
  python organize_files.py ~/Downloads --run --by-date # 年-月フォルダも作る
  python organize_files.py ~/Downloads --run --dedupe  # 重複も退避
  python organize_files.py ~/Downloads --undo          # 直前の実行を元に戻す
"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CATEGORIES = {
    "画像": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".tiff"},
    "動画": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"},
    "音声": {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"},
    "PDF": {".pdf"},
    "文書": {".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".pages"},
    "表計算": {".xls", ".xlsx", ".csv", ".tsv", ".ods", ".numbers"},
    "プレゼン": {".ppt", ".pptx", ".key", ".odp"},
    "圧縮": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "プログラム": {".py", ".js", ".ts", ".html", ".css", ".json", ".sh", ".bat", ".exe", ".msi", ".dmg", ".pkg"},
}
DUP_DIR = "重複"
OTHER = "その他"
LOG_NAME = ".organize_log.json"
CATEGORY_DIRS = set(CATEGORIES) | {DUP_DIR, OTHER}


def category_of(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return OTHER


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        cand = dest.with_name(f"{dest.stem}_{i}{dest.suffix}")
        if not cand.exists():
            return cand
        i += 1


def collect(root: Path):
    """整理対象（root 直下のファイルのみ。サブフォルダや隠しファイルは触らない）"""
    for p in sorted(root.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            yield p


def plan_moves(root: Path, by_date: bool, dedupe: bool):
    moves = []
    seen = {}
    for p in collect(root):
        if dedupe:
            digest = file_hash(p)
            if digest in seen:
                moves.append((p, root / DUP_DIR / p.name))
                continue
            seen[digest] = p
        folder = root / category_of(p)
        if by_date:
            folder = folder / datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")
        moves.append((p, folder / p.name))
    return moves


def run(root: Path, execute: bool, by_date: bool, dedupe: bool):
    moves = plan_moves(root, by_date, dedupe)
    if not moves:
        print("整理対象のファイルがありません。")
        return
    done = []
    for src, dest in moves:
        dest = unique_dest(dest)
        print(f"{src.name}  ->  {dest.relative_to(root)}")
        if execute:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            done.append({"from": str(src), "to": str(dest)})
    if execute:
        (root / LOG_NAME).write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n{len(done)} 件を移動しました。元に戻すには --undo を付けて再実行してください。")
    else:
        print(f"\n{len(moves)} 件が対象です（ドライラン：まだ何も移動していません）。--run で実行します。")


def undo(root: Path):
    log = root / LOG_NAME
    if not log.exists():
        print("取り消せる実行ログがありません。")
        return
    entries = json.loads(log.read_text(encoding="utf-8"))
    for e in reversed(entries):
        src, dest = Path(e["from"]), Path(e["to"])
        if dest.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(unique_dest(src)))
            print(f"戻しました: {src.name}")
    for d in sorted(root.rglob("*"), reverse=True):  # 空になったフォルダを掃除
        if d.is_dir() and d.name in CATEGORY_DIRS or (d.is_dir() and d.parent.name in CATEGORY_DIRS):
            try:
                d.rmdir()
            except OSError:
                pass
    log.unlink()
    print("取り消しが完了しました。")


def main():
    ap = argparse.ArgumentParser(description="フォルダ内のファイルを種類別に整理します")
    ap.add_argument("folder", help="整理するフォルダ（例: ~/Downloads）")
    ap.add_argument("--run", action="store_true", help="実際にファイルを移動する（未指定ならドライラン）")
    ap.add_argument("--by-date", action="store_true", help="カテゴリ内に 年-月 フォルダを作る")
    ap.add_argument("--dedupe", action="store_true", help="内容が同じ重複ファイルを「重複」フォルダへ退避")
    ap.add_argument("--undo", action="store_true", help="直前の実行を元に戻す")
    args = ap.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"フォルダが見つかりません: {root}")
    if root == Path.home() or root == Path(root.anchor):
        sys.exit("ホームフォルダやドライブ直下は危険なため対象にできません。サブフォルダを指定してください。")

    if args.undo:
        undo(root)
    else:
        run(root, args.run, args.by_date, args.dedupe)


if __name__ == "__main__":
    main()
