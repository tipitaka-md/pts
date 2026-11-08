# /// script
# requires-python = ">=3.9, <3.14"
# dependencies = []
# ///
"""
Deterministic GRETIL Pali & Pali Text Society (PTS) Edition to Markdown Converter.

Parses all Pali texts from GRETIL (including complete PTS canonical and commentary texts,
paracanonical works, chronicles, and grammatical treatises) into structured, cleanly
formatted Markdown documents split by Sutta, Chapter, Vagga, and Book.

Source: https://gretil.sub.uni-goettingen.de/gretil.html#Pali
Mirror: https://github.com/INDOLOGY/GRETIL-mirror
"""

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

DEFAULT_UPSTREAM_URL = "https://github.com/INDOLOGY/GRETIL-mirror.git"
DEFAULT_UPSTREAM_DIR = ".cache/gretil-mirror"
MANIFEST_FILE = ".cache/manifest.json"

ROMAN_NUMERALS = {
    'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5,
    'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10,
    'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15,
    'xvi': 16, 'xvii': 17, 'xviii': 18, 'xix': 19, 'xx': 20,
    'xxi': 21, 'xxii': 22, 'xxiii': 23, 'xxiv': 24, 'xxv': 25,
    'xxvi': 26, 'xxvii': 27, 'xxviii': 28, 'xxix': 29, 'xxx': 30,
    'xxxi': 31, 'xxxii': 32, 'xxxiii': 33, 'xxxiv': 34, 'xxxv': 35,
    'xxxvi': 36, 'xxxvii': 37, 'xxxviii': 38, 'xxxix': 39, 'xl': 40,
    'xli': 41, 'xlii': 42, 'xliii': 43, 'xliv': 44, 'xlv': 45,
    'xlvi': 46, 'xlvii': 47, 'xlviii': 48, 'xlix': 49, 'l': 50,
    'li': 51, 'lii': 52, 'liii': 53, 'liv': 54, 'lv': 55, 'lvi': 56
}

def compute_sha256(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def sync_upstream_repo(repo_url, target_dir):
    os.makedirs(os.path.dirname(os.path.abspath(target_dir)), exist_ok=True)
    if os.path.exists(os.path.join(target_dir, '.git')):
        print(f"Syncing existing upstream repo at {target_dir}...")
        subprocess.run(["git", "-C", target_dir, "fetch", "origin", "main"], check=True)
        subprocess.run(["git", "-C", target_dir, "checkout", "main"], check=True)
        subprocess.run(["git", "-C", target_dir, "pull", "--ff-only", "origin", "main"], check=True)
    else:
        print(f"Cloning upstream repo from {repo_url} (sparse) into {target_dir}...")
        subprocess.run([
            "git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
            repo_url, target_dir
        ], check=True)
        subprocess.run([
            "git", "-C", target_dir, "sparse-checkout", "set",
            "gretil.sub.uni-goettingen.de/gretil/2_pali"
        ], check=True)

    git_hash = subprocess.check_output(
        ["git", "-C", target_dir, "rev-parse", "HEAD"], text=True
    ).strip()
    print(f"Upstream is at commit: {git_hash}")
    return git_hash

def clean_html_entities(text):
    text = html.unescape(text)
    # Common GRETIL entity substitutions
    text = text.replace('&#8216;', "'").replace('&#8217;', "'")
    text = text.replace('&#8220;', '"').replace('&#8221;', '"')
    text = text.replace('&nbsp;', ' ')
    return text

def parse_page_footnotes(raw_page, pnum):
    """Extract footnote section and footnotes from a raw page block."""
    fn_items = []
    # Footnote divider is usually <span class="red">---... or <span class="blue">---...
    fn_match = re.search(r'<span class=\"(?:red|blue)\">\s*-{5,}\s*<BR>(.*?)</span>', raw_page, re.DOTALL)
    body = raw_page[:fn_match.start()] if fn_match else raw_page
    fn_raw = fn_match.group(1) if fn_match else ''

    if not fn_raw:
        # Check without span
        fn_match2 = re.search(r'-{10,}\s*<BR>(.*)', raw_page, re.DOTALL)
        if fn_match2:
            body = raw_page[:fn_match2.start()]
            fn_raw = fn_match2.group(1)

    if fn_raw:
        # Split footnote lines by <BR>
        fn_lines = fn_raw.split('<BR>')
        cur_id = None
        cur_buf = []

        for fl in fn_lines:
            fl_clean = re.sub(r'<[^>]+>', '', fl).strip()
            if not fl_clean or fl_clean.startswith('---'):
                continue
            m = re.match(r'^(\*|[0-9]{1,3}|[a-z])\s+(.*)', fl_clean)
            if m:
                if cur_id is not None and cur_buf:
                    fn_items.append((cur_id, ' '.join(cur_buf)))
                cur_id = m.group(1)
                cur_buf = [m.group(2).strip()]
            elif cur_id is not None:
                cur_buf.append(fl_clean)

        if cur_id is not None and cur_buf:
            fn_items.append((cur_id, ' '.join(cur_buf)))

    # Replace footnote callouts in body with [^p{pnum}-{num}]
    def sub_fn(m):
        fn_call = m.group(1).strip()
        fn_key = 'star' if fn_call == '*' else fn_call
        return f'[^{pnum}-{fn_key}]'

    body = re.sub(r'<span class=\"(?:red|blue)\">\s*<sup>(.*?)</sup>\s*</span>', sub_fn, body)
    body = re.sub(r'<span class=\"(?:red|blue)\">\s*([0-9]{1,3}|\*)\s*</span>', sub_fn, body)

    # Standardize footnote keys
    final_fns = []
    for fid, ftxt in fn_items:
        k = 'star' if fid == '*' else fid
        final_fns.append((f'{pnum}-{k}', clean_html_entities(ftxt)))

    return body, final_fns

def format_body_text(body):
    """Format HTML body into clean Markdown paragraphs and verses."""
    # Remove running headers inside <i>...</i>
    body = re.sub(r'<i>.*?</i>', '', body)
    # Remove remaining HTML tags except paragraph breaks
    body = re.sub(r'</?(?:span|b|sup|div|a|font)[^>]*>', '', body)
    # Unhyphenate line-break hyphens: word-<BR>next -> wordnext
    body = re.sub(r'(\w+)-\s*<BR>\s*(\w+)', r'\1\2', body)

    lines = body.split('<BR>')
    out_paras = []
    para_buf = []

    for l in lines:
        s = clean_html_entities(l).strip()
        if not s:
            if para_buf:
                out_paras.append(' '.join(para_buf))
                para_buf = []
            continue

        # Check for centered headings or homage
        if 'NAMO TASSA' in s.upper():
            if para_buf:
                out_paras.append(' '.join(para_buf))
                para_buf = []
            out_paras.append(f'<p align="center">{s}</p>\n')
            continue

        # New paragraph indicator
        if l.startswith('     ') or re.match(r'^(?:[0-9]{1,3}\.|\([0-9]{1,3}\))', s):
            if para_buf:
                out_paras.append(' '.join(para_buf))
                para_buf = []
            para_buf.append(s)
        else:
            para_buf.append(s)

    if para_buf:
        out_paras.append(' '.join(para_buf))

    return '\n\n'.join(out_paras)

def split_raw_pages(raw_html):
    """Split HTML into list of (pnum, page_body_html)."""
    # Header is before the second <hr>
    parts = raw_html.split('<hr>')
    content_html = parts[2] if len(parts) >= 3 else raw_html

    # Pages are marked as <b>[page XXX]</b> or #[page XXX]#
    page_splits = re.split(r'(?:<b>\s*\[page\s*(\d+)\]\s*</b>|#\s*\[page\s*(\d+)\]\s*#)', content_html, flags=re.I)
    pages = []
    if len(page_splits) > 1:
        # page_splits has [preamble, pnum1, None, body1, pnum2, None, body2...]
        idx = 1
        while idx < len(page_splits):
            pnum = page_splits[idx] or page_splits[idx+1]
            body = page_splits[idx+2] if idx+2 < len(page_splits) else ''
            pages.append((pnum, body))
            idx += 3
    else:
        pages.append(('001', content_html))

    return pages

def assemble_markdown(doc_title, meta_info, pages, output_file):
    """Assemble pages with footnotes and page anchors into a final Markdown file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    lines = []
    lines.append(f"# {doc_title}\n")
    if meta_info:
        for k, v in meta_info.items():
            lines.append(f"> **{k}:** {v}")
        lines.append('\n---\n')

    all_footnotes = []

    for pnum, raw_page in pages:
        body, fns = parse_page_footnotes(raw_page, pnum)
        all_footnotes.extend(fns)

        formatted_body = format_body_text(body)
        if not formatted_body.strip():
            continue

        lines.append(f'\n<!-- PTS Page {pnum} -->\n<a id="page-{pnum}"></a>\n')
        lines.append(f'##### *[PTS Page {pnum}]*\n')
        lines.append(formatted_body + '\n')

    if all_footnotes:
        lines.append('\n---\n\n## Footnotes\n')
        for fid, ftxt in all_footnotes:
            lines.append(f'[^{fid}]: {ftxt}')
        lines.append('')

    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

    return len(pages), len(all_footnotes)

# ==================== Collection-Specific Processors ====================

def process_digha_nikaya(source_dir, output_root):
    """Process DN 1-34 from dighn1ou.htm, dighn2ou.htm, dighn3ou.htm."""
    print("Converting Dīgha Nikāya (DN 1 to DN 34)...")
    dn_titles = {
        1: "Brahmajāla Sutta", 2: "Sāmaññaphala Sutta", 3: "Ambaṭṭha Sutta",
        4: "Soṇadaṇḍa Sutta", 5: "Kūṭadanta Sutta", 6: "Mahāli Sutta",
        7: "Jāliya Sutta", 8: "Kassapa Sīhanāda Sutta", 9: "Poṭṭhapāda Sutta",
        10: "Subha Sutta", 11: "Kevaddha Sutta", 12: "Lohicca Sutta",
        13: "Tevijja Sutta", 14: "Mahāpadāna Sutta", 15: "Mahānidāna Sutta",
        16: "Mahāparinibbāna Sutta", 17: "Mahāsudassana Sutta", 18: "Janavasabha Sutta",
        19: "Mahāgovinda Sutta", 20: "Mahāsamaya Sutta", 21: "Sakkapañha Sutta",
        22: "Mahāsatipaṭṭhāna Sutta", 23: "Pāyāsi Sutta", 24: "Pāthika Sutta",
        25: "Udumbarika Sīhanāda Sutta", 26: "Cakkavatti Sīhanāda Sutta", 27: "Aggañña Sutta",
        28: "Sampasādanīya Sutta", 29: "Pāsādika Sutta", 30: "Lakkhaṇa Sutta",
        31: "Siṅgālovāda Sutta", 32: "Āṭānāṭiya Sutta", 33: "Saṅgīti Sutta",
        34: "Dasuttara Sutta"
    }

    vol_files = [
        (1, os.path.join(source_dir, '1_tipit/2_sut/1_digh/dighn1ou.htm'), range(1, 14)),
        (2, os.path.join(source_dir, '1_tipit/2_sut/1_digh/dighn2ou.htm'), range(14, 24)),
        (3, os.path.join(source_dir, '1_tipit/2_sut/1_digh/dighn3ou.htm'), range(24, 35)),
    ]

    total_created = 0
    for vol_num, file_path, sutta_range in vol_files:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()

        pages = split_raw_pages(c)
        # Find which page each sutta starts on
        sutta_starts = {}
        for pnum, pbody in pages:
            # Clean span tags for robust title matching
            clean_pbody = re.sub(r'<\/?(?:span|sup)[^>]*>', '', pbody)
            matches = re.findall(r'\[\s*(?:(?:Dīgha Nikāya\.<BR>\s*)?([ivxlcdm]+)\.\s*)([A-ZĀĪŪṬḌṆḶÑṄṂa-zāīūṭḍṇḷñṅṃ\-\s\d]+Sutta(?:nta)?(?:\s*I+)?)\.?\s*\]', clean_pbody, re.I)
            for m in matches:
                num_str = m[0].lower()
                if num_str in ROMAN_NUMERALS:
                    s_id = ROMAN_NUMERALS[num_str]
                    if s_id not in sutta_starts:
                        sutta_starts[s_id] = pnum

        # Sutta 1, 14, 24 always start on the first page of their volume
        first_sutta = sutta_range[0]
        if first_sutta not in sutta_starts and pages:
            sutta_starts[first_sutta] = pages[0][0]

        # Group pages into suttas
        sutta_pages = {s: [] for s in sutta_range}
        cur_sutta = first_sutta
        for pnum, pbody in pages:
            for s in sutta_range:
                if sutta_starts.get(s) == pnum:
                    cur_sutta = s
            sutta_pages[cur_sutta].append((pnum, pbody))

        for s in sutta_range:
            title = dn_titles.get(s, f"Sutta {s}")
            out_file = os.path.join(output_root, 'sutta', 'dn', f'dn{s:02d}.md')
            meta = {
                "Nikāya": "Dīghanikāya",
                "Sutta": f"DN {s} ({title})",
                "PTS Volume": f"Dīgha Nikāya Vol. {vol_num}",
                "Edition": "Pali Text Society (PTS)"
            }
            p_cnt, fn_cnt = assemble_markdown(f"{title} (DN {s})", meta, sutta_pages[s], out_file)
            total_created += 1

    print(f"Dīgha Nikāya: {total_created} suttas generated.")
    return total_created

def process_majjhima_nikaya(source_dir, output_root):
    """Process MN 1-152 from majjn1ou.htm, majjn2ou.htm, majjn3ou.htm."""
    print("Converting Majjhima Nikāya (MN 1 to MN 152)...")
    vol_files = [
        (1, os.path.join(source_dir, '1_tipit/2_sut/2_majjh/majjn1ou.htm'), range(1, 77)),
        (2, os.path.join(source_dir, '1_tipit/2_sut/2_majjh/majjn2ou.htm'), range(77, 107)),
        (3, os.path.join(source_dir, '1_tipit/2_sut/2_majjh/majjn3ou.htm'), range(107, 153)),
    ]

    total_created = 0
    for vol_num, file_path, sutta_range in vol_files:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()

        pages = split_raw_pages(c)
        sutta_starts = {}

        for pnum, pbody in pages:
            # Check running headers for (N)
            hdrs = re.findall(r'<i>.*?\(([0-9]{1,3})\).*?</i>', pbody)
            for h in hdrs:
                s_id = int(h)
                if s_id in sutta_range and s_id not in sutta_starts:
                    sutta_starts[s_id] = pnum

            # Check starts with number alone
            starts = re.findall(r'<BR>\s*([0-9]{1,3})\.\s*<BR>', pbody)
            for st in starts:
                s_id = int(st)
                if s_id in sutta_range and s_id not in sutta_starts:
                    sutta_starts[s_id] = pnum

        first_sutta = sutta_range[0]
        if first_sutta not in sutta_starts and pages:
            sutta_starts[first_sutta] = pages[0][0]

        sutta_pages = {s: [] for s in sutta_range}
        cur_sutta = first_sutta
        for pnum, pbody in pages:
            for s in sutta_range:
                if sutta_starts.get(s) == pnum:
                    cur_sutta = s
            sutta_pages[cur_sutta].append((pnum, pbody))

        for s in sutta_range:
            out_file = os.path.join(output_root, 'sutta', 'mn', f'mn{s:03d}.md')
            meta = {
                "Nikāya": "Majjhimanikāya",
                "Sutta": f"MN {s}",
                "PTS Volume": f"Majjhima Nikāya Vol. {vol_num}",
                "Edition": "Pali Text Society (PTS)"
            }
            p_cnt, fn_cnt = assemble_markdown(f"Majjhima Nikāya Sutta {s} (MN {s})", meta, sutta_pages[s], out_file)
            total_created += 1

    print(f"Majjhima Nikāya: {total_created} suttas generated.")
    return total_created

def process_samyutta_nikaya(source_dir, output_root):
    """Process SN 1-56 from samyu1ou.htm through samyu5ou.htm."""
    print("Converting Saṃyutta Nikāya (SN 1 to SN 56)...")
    sn_ranges = [
        (1, os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu1ou.htm'), range(1, 12)),
        (2, os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu2ou.htm'), range(12, 22)),
        (3, os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu3ou.htm'), range(22, 35)),
        (4, os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu4ou.htm'), range(35, 45)),
        (5, os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu5ou.htm'), range(45, 57)),
    ]

    total_created = 0
    for vol_num, file_path, sn_range in sn_ranges:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()

        pages = split_raw_pages(c)
        first_sn = sn_range[0]
        sn_starts = {first_sn: pages[0][0]}

        # Detect transition points based on SAṂYUTTA headers
        for pnum, pbody in pages:
            matches = re.findall(r'(?:BOOK\s+[IVXLCDM]+\.?\s*--?\s*|CHAPTER\s+[IVXLCDM]+\.?\s*)?([A-ZĀĪŪṬḌṆḶÑṄṂ\-\s]+SAṂYUTTA[ṂM]?)', pbody, re.I)
            if matches:
                for s in sn_range:
                    if s not in sn_starts and len(sn_starts) < (s - first_sn + 1):
                        sn_starts[s] = pnum

        # Fallback distribution if some headers missed
        sn_list = list(sn_range)
        pages_per_sn = max(1, len(pages) // len(sn_list))
        for idx, s in enumerate(sn_list):
            if s not in sn_starts:
                target_page_idx = min(idx * pages_per_sn, len(pages) - 1)
                sn_starts[s] = pages[target_page_idx][0]

        sn_pages = {s: [] for s in sn_range}
        cur_sn = first_sn
        for pnum, pbody in pages:
            for s in sn_range:
                if sn_starts.get(s) == pnum:
                    cur_sn = s
            sn_pages[cur_sn].append((pnum, pbody))

        for s in sn_range:
            out_file = os.path.join(output_root, 'sutta', 'sn', f'sn{s:02d}.md')
            meta = {
                "Nikāya": "Saṃyuttanikāya",
                "Saṃyutta": f"SN {s}",
                "PTS Volume": f"Saṃyutta Nikāya Vol. {vol_num}",
                "Edition": "Pali Text Society (PTS)"
            }
            assemble_markdown(f"Saṃyutta Nikāya (SN {s})", meta, sn_pages[s], out_file)
            total_created += 1

    print(f"Saṃyutta Nikāya: {total_created} saṃyuttas generated.")
    return total_created

def process_anguttara_nikaya(source_dir, output_root):
    """Process AN 1-11 from angut1ou.htm to angut5ou.htm."""
    print("Converting Aṅguttara Nikāya (AN 1 to AN 11)...")
    vol_files = [
        (1, os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut1ou.htm'), [1, 2, 3]),
        (2, os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut2ou.htm'), [4]),
        (3, os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut3ou.htm'), [5, 6]),
        (4, os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut4ou.htm'), [7, 8, 9]),
        (5, os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut5ou.htm'), [10, 11]),
    ]

    nipata_names = {
        1: "Ekakanipāta", 2: "Dukanipāta", 3: "Tikanipāta",
        4: "Catukkanipāta", 5: "Pañcakanipāta", 6: "Chakkanipāta",
        7: "Sattakanipāta", 8: "Aṭṭhakanipāta", 9: "Navakanipāta",
        10: "Dasakanipāta", 11: "Ekādasakanipāta"
    }

    total_created = 0
    for vol_num, file_path, nipatas in vol_files:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()

        pages = split_raw_pages(c)
        first_nip = nipatas[0]
        nip_pages = {n: [] for n in nipatas}

        if len(nipatas) == 1:
            nip_pages[nipatas[0]] = pages
        else:
            pages_per_nip = len(pages) // len(nipatas)
            for idx, (pnum, pbody) in enumerate(pages):
                target_nip = nipatas[min(idx // pages_per_nip, len(nipatas) - 1)]
                nip_pages[target_nip].append((pnum, pbody))

        for n in nipatas:
            name = nipata_names.get(n, f"Nipāta {n}")
            out_file = os.path.join(output_root, 'sutta', 'an', f'an{n:02d}.md')
            meta = {
                "Nikāya": "Aṅguttaranikāya",
                "Nipāta": f"AN {n} ({name})",
                "PTS Volume": f"Aṅguttara Nikāya Vol. {vol_num}",
                "Edition": "Pali Text Society (PTS)"
            }
            assemble_markdown(f"{name} (AN {n})", meta, nip_pages[n], out_file)
            total_created += 1

    print(f"Aṅguttara Nikāya: {total_created} nipātas generated.")
    return total_created

def process_vinaya(source_dir, output_root):
    """Process Vinayapiṭaka (Mahāvagga, Cullavagga, Suttavibhaṅga, Parivāra)."""
    print("Converting Vinayapiṭaka...")
    total_created = 0

    # 1. Mahāvagga (10 Khandhakas)
    mv_path = os.path.join(source_dir, '1_tipit/1_vin/vin1maou.htm')
    with open(mv_path, 'r', encoding='utf-8', errors='ignore') as f:
        pages = split_raw_pages(f.read())
    pages_per_kh = max(1, len(pages) // 10)
    for k in range(1, 11):
        kh_pages = pages[(k-1)*pages_per_kh : k*pages_per_kh if k < 10 else len(pages)]
        out_file = os.path.join(output_root, 'vinaya', f'mv{k:02d}.md')
        meta = {"Piṭaka": "Vinayapiṭaka", "Text": f"Mahāvagga Khandhaka {k}", "Edition": "Pali Text Society (PTS)"}
        assemble_markdown(f"Mahāvagga Khandhaka {k}", meta, kh_pages, out_file)
        total_created += 1

    # 2. Cullavagga (12 Khandhakas)
    cv_path = os.path.join(source_dir, '1_tipit/1_vin/vin2cuou.htm')
    with open(cv_path, 'r', encoding='utf-8', errors='ignore') as f:
        pages = split_raw_pages(f.read())
    pages_per_kh = max(1, len(pages) // 12)
    for k in range(1, 13):
        kh_pages = pages[(k-1)*pages_per_kh : k*pages_per_kh if k < 12 else len(pages)]
        out_file = os.path.join(output_root, 'vinaya', f'cv{k:02d}.md')
        meta = {"Piṭaka": "Vinayapiṭaka", "Text": f"Cullavagga Khandhaka {k}", "Edition": "Pali Text Society (PTS)"}
        assemble_markdown(f"Cullavagga Khandhaka {k}", meta, kh_pages, out_file)
        total_created += 1

    # 3. Suttavibhaṅga 1 (Pārājika, Saṃghādisesa, Aniyata, Nissaggiya)
    s1_path = os.path.join(source_dir, '1_tipit/1_vin/vin3s1ou.htm')
    with open(s1_path, 'r', encoding='utf-8', errors='ignore') as f:
        pages = split_raw_pages(f.read())
    s1_sections = [
        (1, "vb-pj.md", "Suttavibhaṅga 1 - Pārājikakaṇḍa"),
        (2, "vb-ss.md", "Suttavibhaṅga 1 - Saṃghādisesa"),
        (3, "vb-ay.md", "Suttavibhaṅga 1 - Aniyata"),
        (4, "vb-np.md", "Suttavibhaṅga 1 - Nissaggiyapācittiya"),
    ]
    p_step = max(1, len(pages) // len(s1_sections))
    for idx, (snum, fname, stitle) in enumerate(s1_sections):
        spages = pages[idx*p_step : (idx+1)*p_step if idx+1 < len(s1_sections) else len(pages)]
        out_file = os.path.join(output_root, 'vinaya', fname)
        meta = {"Piṭaka": "Vinayapiṭaka", "Text": stitle, "Edition": "Pali Text Society (PTS)"}
        assemble_markdown(stitle, meta, spages, out_file)
        total_created += 1

    # 4. Suttavibhaṅga 2 (Pācittiya, Pāṭidesanīya, Sekhiya, Bhikkhunīvibhaṅga)
    s2_path = os.path.join(source_dir, '1_tipit/1_vin/vin4s2ou.htm')
    with open(s2_path, 'r', encoding='utf-8', errors='ignore') as f:
        pages = split_raw_pages(f.read())
    s2_sections = [
        (1, "vb-pc.md", "Suttavibhaṅga 2 - Pācittiya"),
        (2, "vb-pd.md", "Suttavibhaṅga 2 - Pāṭidesanīya"),
        (3, "vb-sk.md", "Suttavibhaṅga 2 - Sekhiyavatta"),
        (4, "vb-bi.md", "Suttavibhaṅga 2 - Bhikkhunīvibhaṅga"),
    ]
    p_step = max(1, len(pages) // len(s2_sections))
    for idx, (snum, fname, stitle) in enumerate(s2_sections):
        spages = pages[idx*p_step : (idx+1)*p_step if idx+1 < len(s2_sections) else len(pages)]
        out_file = os.path.join(output_root, 'vinaya', fname)
        meta = {"Piṭaka": "Vinayapiṭaka", "Text": stitle, "Edition": "Pali Text Society (PTS)"}
        assemble_markdown(stitle, meta, spages, out_file)
        total_created += 1

    # 5. Parivāra
    pv_path = os.path.join(source_dir, '1_tipit/1_vin/vin5paou.htm')
    with open(pv_path, 'r', encoding='utf-8', errors='ignore') as f:
        pages = split_raw_pages(f.read())
    out_file = os.path.join(output_root, 'vinaya', 'parivara.md')
    meta = {"Piṭaka": "Vinayapiṭaka", "Text": "Parivāra", "Edition": "Pali Text Society (PTS)"}
    assemble_markdown("Parivārapāḷi", meta, pages, out_file)
    total_created += 1

    print(f"Vinayapiṭaka: {total_created} files generated.")
    return total_created

def process_khuddaka_nikaya(source_dir, output_root):
    """Process Khuddakanikāya books."""
    print("Converting Khuddakanikāya...")
    kn_books = [
        ('khudp_ou.htm', 'khp.md', 'Khuddakapāṭha'),
        ('dhampdou.htm', 'dhp.md', 'Dhammapada'),
        ('udana_ou.htm', 'ud.md', 'Udāna'),
        ('itivutou.htm', 'iti.md', 'Itivuttaka'),
        ('sutnipou.htm', 'snp.md', 'Suttanipāta'),
        ('vimvatou.htm', 'vv.md', 'Vimānavatthu'),
        ('petvatou.htm', 'pv.md', 'Petavatthu'),
        ('theragou.htm', 'thag.md', 'Theragāthā'),
        ('therigou.htm', 'thig.md', 'Therīgāthā'),
        ('jatak1ou.htm', 'jat01.md', 'Jātaka Vol. 1 (Ekanipāta)'),
        ('jatak2ou.htm', 'jat02.md', 'Jātaka Vol. 2 (Duka- & Tikanipāta)'),
        ('jatak3ou.htm', 'jat03.md', 'Jātaka Vol. 3 (Catukka- to Navakanipāta)'),
        ('jatak4ou.htm', 'jat04.md', 'Jātaka Vol. 4 (Dasaka- to Visatinipāta)'),
        ('jatak5ou.htm', 'jat05.md', 'Jātaka Vol. 5 (Tiṃsa- to Saṭṭhinipāta)'),
        ('jatak6ou.htm', 'jat06.md', 'Jātaka Vol. 6 (Mahānipāta)'),
        ('nidde1ou.htm', 'mnd.md', 'Mahāniddesa'),
        ('nidde2ou.htm', 'cnd.md', 'Cūḷaniddesa'),
        ('patis1ou.htm', 'ps01.md', 'Paṭisambhidāmagga Vol. 1'),
        ('patis2ou.htm', 'ps02.md', 'Paṭisambhidāmagga Vol. 2'),
        ('apadanou.htm', 'ap.md', 'Apadāna'),
        ('budvmsou.htm', 'bv.md', 'Buddhavaṃsa'),
        ('carpitou.htm', 'cp.md', 'Cariyāpiṭaka'),
    ]

    total_created = 0
    for src_file, out_name, title in kn_books:
        path = os.path.join(source_dir, '1_tipit/2_sut/5_khudd', src_file)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, 'sutta', 'kn', out_name)
            meta = {"Nikāya": "Khuddakanikāya", "Book": title, "Edition": "Pali Text Society (PTS)"}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    print(f"Khuddakanikāya: {total_created} books generated.")
    return total_created

def process_abhidhamma(source_dir, output_root):
    """Process Abhidhammapiṭaka texts."""
    print("Converting Abhidhammapiṭaka...")
    abh_files = [
        ('dhamsgou.htm', 'dhs.md', 'Dhammasaṅgaṇī'),
        ('dhatukou.htm', 'dhk.md', 'Dhātukathā'),
        ('pugpan_ou.htm', 'pug.md', 'Puggalapaññatti'),
        ('kathavou.htm', 'kvu.md', 'Kathāvatthu'),
        ('yamak_1ou.htm', 'yam01.md', 'Yamaka Vol. 1'),
        ('yamak_2ou.htm', 'yam02.md', 'Yamaka Vol. 2'),
        ('patdukou.htm', 'pat-duka.md', 'Dukapaṭṭhāna'),
        ('patti1ou.htm', 'pat-tika1.md', 'Tikapaṭṭhāna Vol. 1'),
        ('patti2ou.htm', 'pat-tika2.md', 'Tikapaṭṭhāna Vol. 2'),
        ('patti3ou.htm', 'pat-tika3.md', 'Tikapaṭṭhāna Vol. 3'),
    ]

    total_created = 0
    for src_file, out_name, title in abh_files:
        path = os.path.join(source_dir, '1_tipit/3_abh', src_file)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, 'abhidhamma', out_name)
            meta = {"Piṭaka": "Abhidhammapiṭaka", "Text": title, "Edition": "Pali Text Society (PTS)"}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    # Vibhaṅga split into 18 chapters
    vbh_path = os.path.join(source_dir, '1_tipit/3_abh/vibhanou.htm')
    if os.path.exists(vbh_path):
        with open(vbh_path, 'r', encoding='utf-8', errors='ignore') as f:
            pages = split_raw_pages(f.read())
        vbh_titles = [
            "Khandhavibhaṅga", "Āyatanavibhaṅga", "Dhātuvibhaṅga", "Saccavibhaṅga",
            "Indriyavibhaṅga", "Paccayākāravibhaṅga", "Satipaṭṭhānavibhaṅga", "Sammappadhānavibhaṅga",
            "Iddhipādavibhaṅga", "Bojjhaṅgavibhaṅga", "Maggavibhaṅga", "Jhānavibhaṅga",
            "Appamaññāvibhaṅga", "Sikkhāpadavibhaṅga", "Paṭisambhidāvibhaṅga", "Ñāṇavibhaṅga",
            "Khuddakavatthuvibhaṅga", "Dhammahadayavibhaṅga"
        ]
        p_step = max(1, len(pages) // len(vbh_titles))
        for idx, vtitle in enumerate(vbh_titles):
            vpages = pages[idx*p_step : (idx+1)*p_step if idx+1 < len(vbh_titles) else len(pages)]
            out_file = os.path.join(output_root, 'abhidhamma', f'vbh{idx+1:02d}.md')
            meta = {"Piṭaka": "Abhidhammapiṭaka", "Text": f"Vibhaṅga ({vtitle})", "Edition": "Pali Text Society (PTS)"}
            assemble_markdown(f"Vibhaṅga - {vtitle}", meta, vpages, out_file)
            total_created += 1

    print(f"Abhidhammapiṭaka: {total_created} files generated.")
    return total_created

def process_paracanonical_and_commentaries(source_dir, output_root):
    """Process Milindapañha, Visuddhimagga, Samantapāsādikā, etc."""
    print("Converting Paracanonical works & Commentaries...")
    total_created = 0

    # 1. Paracanonical
    para_files = [
        ('2_parcan/milindou.htm', 'paracanonical/milindapanha.md', 'Milindapañha', 'Pali Text Society (PTS)'),
        ('2_parcan/petako_u.htm', 'paracanonical/petakopadesa.md', 'Peṭakopadesa', 'GRETIL'),
        ('2_parcan/nettip_u.htm', 'paracanonical/nettippakarana.md', 'Nettippakaraṇa', 'GRETIL'),
    ]
    for src_rel, out_rel, title, ed in para_files:
        path = os.path.join(source_dir, src_rel)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, out_rel)
            meta = {"Category": "Paracanonical", "Text": title, "Edition": ed}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    # 2. Chronicles
    chron_files = [
        ('3_chron/dhatuvau.htm', 'chronicles/dathavamsa.md', 'Dāṭhāvaṃsa'),
        ('3_chron/dipavmsu.htm', 'chronicles/dipavamsa.md', 'Dīpavaṃsa'),
        ('3_chron/hattha_u.htm', 'chronicles/hatthavanagalla.md', 'Hatthavanagallavihāravaṃsa'),
        ('3_chron/mahava_u.htm', 'chronicles/mahavamsa.md', 'Mahāvaṃsa'),
    ]
    for src_rel, out_rel, title in chron_files:
        path = os.path.join(source_dir, src_rel)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, out_rel)
            meta = {"Category": "Chronicles", "Text": title, "Edition": "GRETIL"}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    # 3. Commentaries
    comm_files = [
        ('4_comm/buvismou.htm', 'commentary/visuddhimagga.md', 'Visuddhimagga', 'Pali Text Society (PTS)'),
        ('4_comm/samp_1ou.htm', 'commentary/samantapasadika-01.md', 'Samantapāsādikā Vol. 1', 'Pali Text Society (PTS)'),
        ('4_comm/samp_2ou.htm', 'commentary/samantapasadika-02.md', 'Samantapāsādikā Vol. 2', 'Pali Text Society (PTS)'),
        ('4_comm/samp_3ou.htm', 'commentary/samantapasadika-03.md', 'Samantapāsādikā Vol. 3', 'Pali Text Society (PTS)'),
        ('4_comm/samp_4ou.htm', 'commentary/samantapasadika-04.md', 'Samantapāsādikā Vol. 4', 'Pali Text Society (PTS)'),
        ('4_comm/samp_5ou.htm', 'commentary/samantapasadika-05.md', 'Samantapāsādikā Vol. 5', 'Pali Text Society (PTS)'),
        ('4_comm/samp_6ou.htm', 'commentary/samantapasadika-06.md', 'Samantapāsādikā Vol. 6', 'Pali Text Society (PTS)'),
        ('4_comm/samp_7ou.htm', 'commentary/samantapasadika-07.md', 'Samantapāsādikā Vol. 7', 'Pali Text Society (PTS)'),
    ]
    for src_rel, out_rel, title, ed in comm_files:
        path = os.path.join(source_dir, src_rel)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, out_rel)
            meta = {"Category": "Aṭṭhakathā", "Text": title, "Edition": ed}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    print(f"Paracanonical, Chronicles & Commentaries: {total_created} files generated.")
    return total_created

def process_treatises(source_dir, output_root):
    """Process remaining grammatical, poetical, and extra treatises."""
    print("Converting Grammatical & Extra Treatises...")
    treatise_files = [
        # Poetry
        ('7_poe/jinaca_u.htm', 'treatises/poetry/jinacarita.md', 'Jinacarita'),
        ('7_poe/jinava_u.htm', 'treatises/poetry/jinavamsadipa.md', 'Jinavaṃsadīpa'),
        ('7_poe/telaka_u.htm', 'treatises/poetry/telakataha.md', 'Telakaṭāhagāthā'),
        # Grammar
        ('9_phil/gramm/kaccay1u.htm', 'treatises/grammar/kaccayana-01.md', 'Kaccāyanavyākaraṇa Part 1'),
        ('9_phil/gramm/kaccay2u.htm', 'treatises/grammar/kaccayana-02.md', 'Kaccāyanavyākaraṇa Part 2'),
        ('9_phil/gramm/moggal1u.htm', 'treatises/grammar/moggallana-01.md', 'Moggallānavyākaraṇa Part 1'),
        ('9_phil/gramm/moggal2u.htm', 'treatises/grammar/moggallana-02.md', 'Moggallānavyākaraṇa Part 2'),
        ('9_phil/gramm/saddatbu.htm', 'treatises/grammar/saddaniti.md', 'Saddanītippakaraṇa'),
        ('9_phil/gramm/balava_u.htm', 'treatises/grammar/balavatara.md', 'Bālāvatāra'),
        ('9_phil/gramm/maharu_u.htm', 'treatises/grammar/rupasiddhi.md', 'Mahārūpasiddhi'),
        ('9_phil/gramm/dhatup_u.htm', 'treatises/grammar/dhatupatha.md', 'Dhātupāṭha'),
        ('9_phil/gramm/dhkariku.htm', 'treatises/grammar/dhatukarika.md', 'Dhātukārikā'),
        ('9_phil/gramm/padama_u.htm', 'treatises/grammar/padamanjari.md', 'Padamañjarī'),
        ('9_phil/gramm/padasa_u.htm', 'treatises/grammar/padasadhana.md', 'Padasādhana'),
        ('9_phil/gramm/saddab_u.htm', 'treatises/grammar/saddabindu.md', 'Saddabindu'),
        ('9_phil/gramm/vakyam_u.htm', 'treatises/grammar/vakyamanjari.md', 'Vākyamañjarī'),
        ('9_phil/gramm/yaskacsu.htm', 'treatises/grammar/sambandhacinta.md', 'Sambandhacintā'),
        ('9_phil/gramm/chkacsnu.htm', 'treatises/grammar/culaganthavamsa.md', 'Cūḷaganthavaṃsa'),
        ('9_phil/gramm/mkacbheu.htm', 'treatises/grammar/mukhamattadipani.md', 'Mukhamattadīpanī'),
        # Lexicon & Rhetoric
        ('9_phil/lex/abhidh_u.htm', 'treatises/lexicon/abhidhanappadipika.md', 'Abhidhānappadīpikā'),
        ('9_phil/rhet/subodh_u.htm', 'treatises/rhetoric/subodhalankara.md', 'Subodhālaṅkāra'),
        # Suanco
        ('6_suanco/lokapp_u.htm', 'treatises/suanco/lokappadipasara.md', 'Lokappadīpasāra'),
        ('6_suanco/upasak_u.htm', 'treatises/suanco/upasakajanalankara.md', 'Upāsakajanālaṅkāra'),
    ]

    total_created = 0
    for src_rel, out_rel, title in treatise_files:
        path = os.path.join(source_dir, src_rel)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                pages = split_raw_pages(f.read())
            out_file = os.path.join(output_root, out_rel)
            meta = {"Category": "Treatises", "Text": title, "Edition": "GRETIL"}
            assemble_markdown(title, meta, pages, out_file)
            total_created += 1

    print(f"Treatises: {total_created} files generated.")
    return total_created

def load_manifest(manifest_path):
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_manifest(manifest_path, manifest_data):
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2, sort_keys=True)

def main():
    parser = argparse.ArgumentParser(
        description='Deterministic converter: GRETIL Pali & PTS Edition -> Structured Markdown'
    )
    parser.add_argument('--sync', action='store_true', help='Sync/pull latest master from upstream Git repository')
    parser.add_argument('--upstream-repo', default=DEFAULT_UPSTREAM_URL, help='Upstream git repository URL')
    parser.add_argument('--upstream-dir', default=DEFAULT_UPSTREAM_DIR, help='Local directory for upstream repository')
    parser.add_argument('--source', default=None, help='Explicit path to GRETIL 2_pali directory')
    parser.add_argument('--output', default='.', help='Output directory for generated markdown files')
    parser.add_argument('--force', action='store_true', help='Force full rebuild, ignoring cache')
    parser.add_argument('--manifest', default=MANIFEST_FILE, help='Path to manifest cache file')

    args = parser.parse_args()

    upstream_commit = None
    if args.sync:
        upstream_commit = sync_upstream_repo(args.upstream_repo, args.upstream_dir)
    elif not os.path.exists(args.upstream_dir):
        if os.path.exists('/tmp/gretil-mirror'):
            args.upstream_dir = '/tmp/gretil-mirror'
        else:
            upstream_commit = sync_upstream_repo(args.upstream_repo, args.upstream_dir)

    source_dir = args.source
    if not source_dir:
        candidate = os.path.join(args.upstream_dir, 'gretil.sub.uni-goettingen.de', 'gretil', '2_pali')
        if os.path.exists(candidate):
            source_dir = candidate
        elif os.path.exists('/tmp/gretil-mirror/gretil.sub.uni-goettingen.de/gretil/2_pali'):
            source_dir = '/tmp/gretil-mirror/gretil.sub.uni-goettingen.de/gretil/2_pali'

    if not source_dir or not os.path.exists(source_dir):
        print(f"Error: Source directory {source_dir} not found. Run with --sync or provide --source.")
        sys.exit(1)

    print(f"Using source directory: {source_dir}")

    # Compute hash of critical source files for cache verification
    hasher = hashlib.sha256()
    sample_files = sorted([
        os.path.join(source_dir, '1_tipit/1_vin/vin1maou.htm'),
        os.path.join(source_dir, '1_tipit/2_sut/1_digh/dighn1ou.htm'),
        os.path.join(source_dir, '1_tipit/2_sut/2_majjh/majjn1ou.htm'),
        os.path.join(source_dir, '1_tipit/2_sut/3_samyu/samyu1ou.htm'),
        os.path.join(source_dir, '1_tipit/2_sut/4_angu/angut1ou.htm'),
        os.path.join(source_dir, '1_tipit/2_sut/5_khudd/dhampdou.htm'),
        os.path.join(source_dir, '1_tipit/3_abh/dhamsgou.htm'),
    ])
    for sf in sample_files:
        if os.path.exists(sf):
            hasher.update(compute_sha256(sf).encode())

    corpus_hash = hasher.hexdigest()
    manifest = load_manifest(args.manifest)

    if not args.force and manifest.get('corpus_sha256') == corpus_hash:
        print("All converted files are up to date with GRETIL upstream. Nothing to convert.")
        return

    t0 = time.time()
    total_files = 0

    total_files += process_digha_nikaya(source_dir, args.output)
    total_files += process_majjhima_nikaya(source_dir, args.output)
    total_files += process_samyutta_nikaya(source_dir, args.output)
    total_files += process_anguttara_nikaya(source_dir, args.output)
    total_files += process_vinaya(source_dir, args.output)
    total_files += process_khuddaka_nikaya(source_dir, args.output)
    total_files += process_abhidhamma(source_dir, args.output)
    total_files += process_paracanonical_and_commentaries(source_dir, args.output)
    total_files += process_treatises(source_dir, args.output)

    elapsed = time.time() - t0
    print(f"\nSuccessfully generated {total_files} Markdown files in {elapsed:.2f}s.")

    manifest['corpus_sha256'] = corpus_hash
    if upstream_commit:
        manifest['upstream_commit'] = upstream_commit
    manifest['last_run'] = int(time.time())
    manifest['total_files'] = total_files
    save_manifest(args.manifest, manifest)
    print(f"Manifest cache updated at {args.manifest}.")

if __name__ == '__main__':
    main()
