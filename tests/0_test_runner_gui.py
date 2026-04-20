import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


ROOT_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT_DIR / "tests"

TEST_FILES = [
    ("聊天接口测试", "test_chat_api.py"),
    ("工作流接口测试", "test_workflow_api.py"),
    ("项目接口测试", "test_project_api.py"),
]


class TestRunnerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("StyleSync Test Runner")
        self.root.geometry("860x620")

        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.is_running = False
        self.test_vars: dict[str, tk.BooleanVar] = {}

        self._build_ui()
        self.root.after(120, self._poll_output_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)

        title = ttk.Label(
            container,
            text="StyleSync 测试面板",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            container,
            text="勾选要运行的测试文件，底层仍然使用 pytest。",
        )
        subtitle.pack(anchor="w", pady=(4, 12))

        select_frame = ttk.LabelFrame(container, text="测试选择", padding=12)
        select_frame.pack(fill="x")

        for label, filename in TEST_FILES:
            var = tk.BooleanVar(value=True)
            self.test_vars[filename] = var
            ttk.Checkbutton(
                select_frame,
                text=f"{label}  ({filename})",
                variable=var,
            ).pack(anchor="w", pady=3)

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(12, 8))

        self.run_selected_button = ttk.Button(
            button_row,
            text="运行选中测试",
            command=self.run_selected_tests,
        )
        self.run_selected_button.pack(side="left")

        self.run_all_button = ttk.Button(
            button_row,
            text="运行全部测试",
            command=self.run_all_tests,
        )
        self.run_all_button.pack(side="left", padx=(8, 0))

        self.stop_button = ttk.Button(
            button_row,
            text="终止运行",
            command=self.stop_tests,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))

        self.clear_button = ttk.Button(
            button_row,
            text="清空输出",
            command=self.clear_output,
        )
        self.clear_button.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="状态：待运行")
        ttk.Label(container, textvariable=self.status_var).pack(anchor="w", pady=(0, 8))

        self.output = scrolledtext.ScrolledText(
            container,
            wrap="word",
            font=("Consolas", 10),
            height=28,
        )
        self.output.pack(fill="both", expand=True)
        self.output.insert("end", f"项目根目录: {ROOT_DIR}\n")
        self.output.insert("end", f"当前 Python: {sys.executable}\n\n")
        self.output.configure(state="disabled")

    def _set_running_state(self, running: bool):
        self.is_running = running
        state = "disabled" if running else "normal"
        self.run_selected_button.config(state=state)
        self.run_all_button.config(state=state)
        self.stop_button.config(state="normal" if running else "disabled")

    def _append_output(self, text: str):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _poll_output_queue(self):
        while not self.output_queue.empty():
            kind, message = self.output_queue.get_nowait()
            if kind == "output":
                self._append_output(message)
            elif kind == "done":
                self._set_running_state(False)
                self.status_var.set(message)
                self.process = None
        self.root.after(120, self._poll_output_queue)

    def _selected_files(self) -> list[Path]:
        selected = [
            TESTS_DIR / filename
            for filename, selected_var in self.test_vars.items()
            if selected_var.get()
        ]
        return selected

    def run_selected_tests(self):
        selected = self._selected_files()
        if not selected:
            messagebox.showwarning("未选择测试", "请至少勾选一个测试文件。")
            return
        self._run_pytest(selected)

    def run_all_tests(self):
        selected = [TESTS_DIR / filename for _, filename in TEST_FILES]
        self._run_pytest(selected)

    def _run_pytest(self, test_files: list[Path]):
        if self.is_running:
            messagebox.showinfo("测试运行中", "当前已有测试在运行，请先等待或终止。")
            return

        missing_files = [str(path.name) for path in test_files if not path.exists()]
        if missing_files:
            messagebox.showerror("文件不存在", f"缺少测试文件：{', '.join(missing_files)}")
            return

        self._set_running_state(True)
        selected_names = ", ".join(path.name for path in test_files)
        self.status_var.set("状态：测试运行中")
        self._append_output(f"\n=== 开始运行: {selected_names} ===\n")

        thread = threading.Thread(
            target=self._run_pytest_worker,
            args=(test_files,),
            daemon=True,
        )
        thread.start()

    def _run_pytest_worker(self, test_files: list[Path]):
        cmd = [sys.executable, "-m", "pytest", *[str(path) for path in test_files]]
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.output_queue.put(("output", line))

            return_code = self.process.wait()
            if return_code == 0:
                self.output_queue.put(("done", "状态：测试通过"))
            elif return_code < 0:
                self.output_queue.put(("done", "状态：测试已终止"))
            else:
                self.output_queue.put(("done", f"状态：测试失败（退出码 {return_code}）"))
        except Exception as exc:
            self.output_queue.put(("output", f"\n[ERROR] 无法启动 pytest: {exc}\n"))
            self.output_queue.put(("done", "状态：启动失败"))

    def stop_tests(self):
        if not self.process or self.process.poll() is not None:
            return

        try:
            self.process.terminate()
            self._append_output("\n[SYSTEM] 已发送终止信号。\n")
            self.status_var.set("状态：正在终止测试")
        except Exception as exc:
            messagebox.showerror("终止失败", str(exc))

    def clear_output(self):
        if self.is_running:
            messagebox.showinfo("请稍后", "测试运行中时不建议清空输出。")
            return
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", f"项目根目录: {ROOT_DIR}\n")
        self.output.insert("end", f"当前 Python: {sys.executable}\n\n")
        self.output.configure(state="disabled")

    def _on_close(self):
        if self.is_running:
            if not messagebox.askyesno("确认退出", "当前测试仍在运行，确定要退出吗？"):
                return
            self.stop_tests()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = TestRunnerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
