import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class BaiduPusherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("百度链接提交工具")
        self.geometry("960x720")

        self.crawled_urls = set()
        self.is_crawling = False
        self.is_pushing = False
        self.msg_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        cfg = ttk.LabelFrame(self, text="配置")
        cfg.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(cfg, text="API 地址:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        self.api_var = tk.StringVar(
            value="https://data.zz.baidu.com/urls?site=YOUR_SITE&token=YOUR_SECRET"
        )
        ttk.Entry(cfg, textvariable=self.api_var).grid(
            row=0, column=1, sticky=tk.EW, padx=6, pady=6
        )

        ttk.Label(cfg, text="起始 URL:").grid(row=1, column=0, sticky=tk.W, padx=6, pady=6)
        self.start_var = tk.StringVar(value="https://example.com")
        ttk.Entry(cfg, textvariable=self.start_var).grid(
            row=1, column=1, sticky=tk.EW, padx=6, pady=6
        )

        opt = ttk.Frame(cfg)
        opt.grid(row=2, column=1, sticky=tk.W, padx=6, pady=6)
        ttk.Label(opt, text="最大抓取:").pack(side=tk.LEFT)
        self.max_var = tk.StringVar(value="1000")
        ttk.Entry(opt, textvariable=self.max_var, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Label(opt, text="最大深度:").pack(side=tk.LEFT, padx=(12, 0))
        self.depth_var = tk.StringVar(value="3")
        ttk.Entry(opt, textvariable=self.depth_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(opt, text="延迟(秒):").pack(side=tk.LEFT, padx=(12, 0))
        self.delay_var = tk.StringVar(value="0.2")
        ttk.Entry(opt, textvariable=self.delay_var, width=6).pack(side=tk.LEFT, padx=4)

        cfg.columnconfigure(1, weight=1)

        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill=tk.X, padx=10, pady=4)
        self.btn_crawl = ttk.Button(btn_bar, text="开始抓取", command=self.start_crawl)
        self.btn_crawl.pack(side=tk.LEFT, padx=4)
        self.btn_push = ttk.Button(
            btn_bar, text="开始提交", command=self.start_push, state=tk.DISABLED
        )
        self.btn_push.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="清空 URL", command=self.clear_urls).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="导出 URL", command=self.export_urls).pack(side=tk.LEFT, padx=4)

        list_frame = ttk.LabelFrame(self, text="已抓取 URL（点击可编辑 API）")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.url_listbox = tk.Listbox(list_frame, font=("Consolas", 9))
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.url_listbox.yview)
        self.url_listbox.config(yscrollcommand=sb.set)
        self.url_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=4)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var, anchor=tk.W).pack(
            fill=tk.X, padx=12
        )

        log_frame = ttk.LabelFrame(self, text="日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, font=("Consolas", 9), state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_queue(self):
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log(data)
                elif kind == "urls_bulk":
                    for u in data:
                        self.url_listbox.insert(tk.END, u)
                elif kind == "progress":
                    self.progress["value"] = data
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "crawl_done":
                    self.is_crawling = False
                    self.btn_crawl.config(state=tk.NORMAL)
                    self.btn_push.config(
                        state=tk.NORMAL if self.crawled_urls else tk.DISABLED
                    )
                    self.log(f"抓取完成，共 {len(self.crawled_urls)} 个 URL")
                elif kind == "push_done":
                    self.is_pushing = False
                    self.btn_crawl.config(state=tk.NORMAL)
                    self.btn_push.config(
                        state=tk.NORMAL if self.crawled_urls else tk.DISABLED
                    )
                    if data:
                        if "失败" in data or "错误" in data or data.startswith("提交失败"):
                            messagebox.showerror("提交结果", data)
                        else:
                            messagebox.showinfo("提交结果", data)
                elif kind == "error":
                    self.is_crawling = False
                    self.is_pushing = False
                    self.btn_crawl.config(state=tk.NORMAL)
                    self.btn_push.config(
                        state=tk.NORMAL if self.crawled_urls else tk.DISABLED
                    )
                    messagebox.showerror("错误", data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _validate_int(self, var, name, default=10):
        try:
            v = int(var.get())
            if v < 0:
                raise ValueError
            return v
        except ValueError:
            messagebox.showwarning("提示", f"{name} 必须是非负整数")
            return None

    def _validate_float(self, var, name, default=0.0):
        try:
            v = float(var.get())
            if v < 0:
                raise ValueError
            return v
        except ValueError:
            messagebox.showwarning("提示", f"{name} 必须是非负数")
            return None

    @staticmethod
    def _decode_html(content: bytes) -> str:
        ct_charset = None
        try:
            head = content[:1024].decode("ascii", errors="ignore")
            m = re.search(rb'charset=["\']?([\w-]+)', head, re.I)
            if m:
                ct_charset = m.group(1).decode("ascii", errors="ignore").lower()
        except Exception:
            pass

        candidates = []
        if ct_charset:
            candidates.append(ct_charset)
        candidates += ["utf-8", "gb18030", "gbk", "big5"]

        for enc in candidates:
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return content.decode("utf-8", errors="replace")

    def start_crawl(self):
        if self.is_crawling or self.is_pushing:
            return
        start = self.start_var.get().strip()
        if not start.startswith(("http://", "https://")):
            messagebox.showwarning("提示", "请输入以 http:// 或 https:// 开头的 URL")
            return
        max_n = self._validate_int(self.max_var, "最大抓取数")
        if max_n is None:
            return
        max_depth = self._validate_int(self.depth_var, "最大深度")
        if max_depth is None:
            return
        delay = self._validate_float(self.delay_var, "延迟")
        if delay is None:
            return

        self.crawled_urls.clear()
        self.url_listbox.delete(0, tk.END)
        self.progress["value"] = 0
        self.progress["maximum"] = max_n
        self.is_crawling = True
        self.btn_crawl.config(state=tk.DISABLED)
        self.btn_push.config(state=tk.DISABLED)

        threading.Thread(
            target=self._crawl_worker,
            args=(start, max_n, max_depth, delay),
            daemon=True,
        ).start()

    def _crawl_worker(self, start, max_n, max_depth, delay):
        try:
            start_domain = urlparse(start).netloc
            visited = set()
            pending = [(start, 0)]
            buffer = []

            session = requests.Session()
            session.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )

            self.msg_queue.put(("status", f"抓取中: {start_domain}"))
            self.msg_queue.put(("log", f"开始抓取 {start}（深度 ≤ {max_depth}）"))

            while pending and len(self.crawled_urls) < max_n:
                url, depth = pending.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                try:
                    resp = session.get(url, timeout=10, allow_redirects=True)
                except Exception as e:
                    self.msg_queue.put(("log", f"请求失败 {url}: {e}"))
                    continue

                if resp.status_code != 200:
                    self.msg_queue.put(("log", f"非 200 {resp.status_code}: {url}"))
                    continue
                ctype = resp.headers.get("Content-Type", "")
                if "text/html" not in ctype:
                    self.crawled_urls.add(resp.url)
                    buffer.append(resp.url)
                    continue

                html = self._decode_html(resp.content)
                self.crawled_urls.add(resp.url)
                buffer.append(resp.url)

                if len(buffer) >= 20:
                    self.msg_queue.put(("urls_bulk", buffer))
                    self.msg_queue.put((
                        "progress", min(len(self.crawled_urls), max_n)
                    ))
                    self.msg_queue.put((
                        "status", f"已抓取 {len(self.crawled_urls)}/{max_n}"
                    ))
                    buffer = []

                if depth < max_depth:
                    try:
                        soup = BeautifulSoup(html, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = a.get("href", "").strip()
                            if not href or href.startswith((
                                "javascript:", "mailto:", "tel:", "#"
                            )):
                                continue
                            full = urljoin(resp.url, href)
                            full = full.split("#")[0]
                            if not full:
                                continue
                            p = urlparse(full)
                            if p.netloc == start_domain and p.scheme in ("http", "https"):
                                if full not in visited and full not in self.crawled_urls:
                                    pending.append((full, depth + 1))
                    except Exception as e:
                        self.msg_queue.put(("log", f"解析失败 {url}: {e}"))

                if delay > 0:
                    time.sleep(delay)

            if buffer:
                self.msg_queue.put(("urls_bulk", buffer))
            self.msg_queue.put(("progress", min(len(self.crawled_urls), max_n)))
            self.msg_queue.put(("status", f"抓取完成: {len(self.crawled_urls)}"))
            self.msg_queue.put(("crawl_done", None))
        except Exception as e:
            self.msg_queue.put(("error", f"抓取异常: {e}"))

    def start_push(self):
        if self.is_pushing or not self.crawled_urls:
            return
        api = self.api_var.get().strip()
        if not api.startswith(("http://", "https://")):
            messagebox.showwarning("提示", "API 地址格式错误")
            return
        if "site=" not in api or "token=" not in api:
            if not messagebox.askyesno(
                "确认", "API 地址中未检测到 site/token 参数，是否继续？"
            ):
                return

        self.is_pushing = True
        self.btn_crawl.config(state=tk.DISABLED)
        self.btn_push.config(state=tk.DISABLED)
        threading.Thread(target=self._push_worker, args=(api,), daemon=True).start()

    def _push_worker(self, api):
        try:
            urls = list(self.crawled_urls)
            total = len(urls)
            self.msg_queue.put(("log", f"开始提交，共 {total} 个 URL"))
            self.msg_queue.put(("status", f"提交中: 0/{total}"))

            success = 0
            fail = 0
            last_error = None
            for i in range(0, total, 2000):
                batch = urls[i:i+2000]
                body = "\n".join(batch)
                try:
                    resp = requests.post(
                        api,
                        data=body.encode("utf-8"),
                        headers={"Content-Type": "text/plain"},
                        timeout=30,
                    )
                    self.msg_queue.put((
                        "log",
                        f"批次 {i//2000+1}: HTTP {resp.status_code} "
                        f"({len(resp.text)} 字节)"
                    ))

                    if resp.status_code != 200:
                        fail += 1
                        try:
                            j = resp.json()
                            err_msg = j.get("message", j.get("error", resp.text[:200]))
                        except ValueError:
                            err_msg = resp.text[:200]
                        last_error = f"HTTP {resp.status_code} — {err_msg}"
                        self.msg_queue.put(("log", f"  响应: {resp.text[:500]}"))
                        if resp.status_code in (401, 403):
                            last_error = (
                                f"HTTP {resp.status_code} — token 无效或站点未验证"
                            )
                            break
                        if "over quota" in last_error.lower():
                            break
                        continue

                    try:
                        result = resp.json()
                    except ValueError:
                        fail += 1
                        last_error = "响应非 JSON"
                        self.msg_queue.put((
                            "log", f"  响应: {resp.text[:500]}"
                        ))
                        continue

                    if result.get("error") is not None:
                        fail += 1
                        err = result.get("error")
                        last_error = f"百度报错: {err}"
                        self.msg_queue.put(("log", f"  百度 error: {err}"))
                        continue

                    s = result.get("success", 0)
                    remain = result.get("remain", "?")
                    invalid = result.get("not_valid", [])
                    same = result.get("not_same_site", [])
                    success += s
                    self.msg_queue.put((
                        "log",
                        f"  成功 {s}, 剩余 {remain}, "
                        f"无效 {len(invalid)}, 跨域 {len(same)}"
                    ))
                    if invalid:
                        self.msg_queue.put((
                            "log", f"  无效示例: {invalid[:3]}"
                        ))
                except Exception as e:
                    fail += 1
                    last_error = str(e)
                    self.msg_queue.put(("log", f"批次 {i//2000+1} 异常: {e}"))

                self.msg_queue.put((
                    "status", f"提交中: {min(i+2000, total)}/{total}"
                ))
                time.sleep(1)

            if total == 0:
                summary = "没有可提交的 URL"
            elif success == 0 and fail > 0 and last_error:
                summary = f"提交失败：{last_error}\n成功 0 / {total}"
            else:
                summary = f"成功 {success} / {total}（失败 {fail} 批）"

            self.msg_queue.put(("log", f"=== {summary} ==="))
            self.msg_queue.put(("status", summary.split("\n")[0]))
            self.msg_queue.put(("push_done", summary))
        except Exception as e:
            self.msg_queue.put(("error", f"提交异常: {e}"))

    def clear_urls(self):
        if self.is_crawling or self.is_pushing:
            return
        self.crawled_urls.clear()
        self.url_listbox.delete(0, tk.END)
        self.progress["value"] = 0
        self.status_var.set("就绪")
        self.log("已清空 URL 列表")

    def export_urls(self):
        if not self.crawled_urls:
            messagebox.showinfo("提示", "没有 URL 可导出")
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(self.crawled_urls)))
        self.log(f"已导出 {len(self.crawled_urls)} 条到 {path}")


if __name__ == "__main__":
    app = BaiduPusherApp()
    app.mainloop()
