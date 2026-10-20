"""Audit AMI's primary chooser manifest without fetching corpus audio."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw/ami-meeting-corpus"


class Options(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "option":
            value = dict(attrs).get("value", "")
            if re.fullmatch(r"[A-Z]{2}\d+[a-z]?", value):
                self.ids.append(value)


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("--headers", action="store_true")
    args = args_parser.parse_args()
    parser = Options()
    parser.feed((RAW / "download.html").read_text())
    fields = [("sessionID", value) for value in parser.ids]
    fields += [(site, part) for site in ["ES", "IS", "TS"] for part in "abcd"]
    fields += [("mediaType", "Mix-Headset"), ("detailed", "yes")]
    url = "https://homepages.inf.ed.ac.uk/cgi/simonk/AMI/estimate.cgi?" + urlencode(
        fields
    )
    data = subprocess.run(
        ["curl", "-fsSL", "--max-time", "90", "--max-filesize", "2000000", url],
        capture_output=True,
        check=True,
    ).stdout
    (RAW / "all-mixes-estimate.html").write_bytes(data)
    text = data.decode()
    urls = sorted(
        set(
            re.findall(
                r"https://groups\.inf\.ed\.ac\.uk/ami/AMICorpusMirror/[^\\\s<>\'\"]+\.wav",
                text,
            )
        )
    )
    result = {
        "chooser_url": url,
        "mix_count": len(urls),
        "mix_urls": urls,
        "source_size_text": re.findall(
            r"Size of the data to be downloaded: ([^<]+)", text
        ),
        "audio_downloaded": False,
    }
    if args.headers:

        def head(url):
            response = subprocess.run(
                ["curl", "-fsSI", "--max-time", "45", url],
                capture_output=True,
                check=True,
            ).stdout.decode()
            lengths = re.findall(r"(?im)^content-length:\s*(\d+)", response)
            assert lengths, url
            return {"url": url, "bytes": int(lengths[-1])}

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            result["files"] = list(pool.map(head, urls))
        result["audio_bytes"] = sum(file["bytes"] for file in result["files"])
    (RAW / "primary-mix-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        {
            "mix_count": len(urls),
            "source_size_text": result["source_size_text"],
            "audio_bytes": result.get("audio_bytes"),
        }
    )


if __name__ == "__main__":
    main()
