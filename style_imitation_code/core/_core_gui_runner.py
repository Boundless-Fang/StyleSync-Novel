# --- File: core/_core_gui_runner.py --- 
import sys 
import argparse 

def safe_run_app(app_class, headless_func, **headless_kwargs): 
    """ 
    统一的安全启动器： 
    1. 自动解析命令行参数 
    2. 无参时尝试启动 GUI (安全拦截 Linux 无头环境异常) 
    3. 有参时静默分发给 headless_func 
    """ 
    parser = argparse.ArgumentParser() 
    parser.add_argument("--target_file", type=str, default="") 
    parser.add_argument("--project", type=str, default="") 
    parser.add_argument("--model", type=str, default="deepseek-chat") 
    parser.add_argument("--character", type=str, default="") 
    parser.add_argument("--mode", type=str, default="") 
    parser.add_argument("--json_data", type=str, default="") 
    parser.add_argument("--chapter", type=str, default="") 
    parser.add_argument("--brief", type=str, default="") 
    args, unknown = parser.parse_known_args() 

    # GUI 启动分支 
    if not args.target_file and len(sys.argv) == 1 and not args.mode and not args.chapter: 
        try: 
            import tkinter as tk 
            from tkinter import ttk, filedialog, messagebox
            root = tk.Tk() 
            app = app_class(root) 
            root.mainloop() 
        except Exception as e: 
            print(f"\n[系统拦截] 无法启动图形界面，当前环境可能缺少显示驱动。") 
            print(f"底层错误: {e}\n[操作建议] 请通过 Web 工作台或命令行参数执行。") 
            sys.exit(1) 
    
    # 静默执行分支 
    else: 
        if not args.target_file and unknown and not unknown[0].startswith('--'): 
            args.target_file = unknown[0] 
        
        # 将解析到的参数更新到传入的字典中 
        if 'target_file' in headless_kwargs: headless_kwargs['target_file'] = args.target_file 
        if 'file_path' in headless_kwargs: headless_kwargs['file_path'] = args.target_file 
        if 'project_name' in headless_kwargs: headless_kwargs['project_name'] = args.project 
        if 'model' in headless_kwargs: headless_kwargs['model'] = args.model 
        if 'character_list_str' in headless_kwargs: headless_kwargs['character_list_str'] = args.character 
        if 'mode' in headless_kwargs: headless_kwargs['mode'] = args.mode 
        if 'json_string' in headless_kwargs: headless_kwargs['json_string'] = args.json_data 
        if 'json_data' in headless_kwargs: headless_kwargs['json_data'] = args.json_data 
        if 'chapter_name' in headless_kwargs: headless_kwargs['chapter_name'] = args.chapter 
        if 'chapter_brief_json' in headless_kwargs: headless_kwargs['chapter_brief_json'] = args.brief 
        
        headless_func(**headless_kwargs) 
