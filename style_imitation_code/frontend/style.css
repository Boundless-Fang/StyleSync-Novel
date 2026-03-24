const { createApp, ref, computed, watch, onMounted } = Vue;

createApp({
    setup() {
        // 全局配置
        const config = ref({
            showWorkspace: true, layoutRatio: 45, fontSize: 14,
            apiKey: localStorage.getItem('deepseekApiKey') || '',
            globalForbidden: '政治,暴力,色情',
            retryLimit: 1, forbiddenTolerance: 3 
        });

        // 消息与历史会话数据模型
        const getNewChatTemplate = (id, title) => ({
            id, title, model: 'deepseek-chat', systemPrompt: '', localForbidden: '',
            temperature: 0.5, top_p: 0.4, max_tokens: null, 
            stats: { local_hit_count: 0, total_tokens: 0 }, messages: []
        });

        const chats = ref([ getNewChatTemplate('chat_1', '默认对话') ]);
        const currentChatId = ref('chat_1');
        const chatInput = ref('');
        const isGenerating = ref(false);
        let abortController = null;

        // 工作台状态
        const activeTab = ref('editor');
        const projects = ref([]);
        const currentProject = ref('');
        const chapters = ref([]);
        const currentChapter = ref('');
        const editorContent = ref('');
        const saveStatus = ref('已保存');
        let saveTimeout = null;

        // 自动化工作流参数
        const references = ref([]);
        const selectedReference = ref('');
        
        // 新增：自动流水线模式参数
        const styleExtractMode = ref('auto');
        const autoPipelineType = ref('fanfic');
        const autoStyleCharNames = ref('');
        const isAutoRunning = ref(false);
        const autoRunProgress = ref('');
        
        // 文件上传响应式变量
        const fileInput = ref(null);
        const uploadFileName = ref('');
        let uploadFileObj = null;

        // 任务管理
        const taskList = ref([]);
        const showAllTasks = ref(false);
        const visibleTasks = computed(() => showAllTasks.value ? taskList.value : taskList.value.slice(0, 5));

        const pollTasks = async () => {
            try {
                const res = await fetch('/api/tasks');
                if(res.ok) {
                    taskList.value = await res.json();
                }
            } catch(e) { console.error("轮询任务失败", e); }
        };
        // 启动轮询
        setInterval(pollTasks, 2000);

        const projectActionMode = ref('create'); // 新增：模式选择
        const newProjectName = ref('');
        const existingProjectSelect = ref('');
        const newProjectBranch = ref('原创');
        const newProjectReferenceStyle = ref('');
        const availableStyles = ref([]);
        
        const workflowProjectScript = ref('f5b');
        const workflowProjectModel = ref('deepseek-chat');
        
        const workflowStyleScript = ref('f1a');
        const workflowStyleModel = ref('deepseek-chat');

        const workflowCharName = ref('');
        const workflowCharSelect = ref('');
        const workflowChapterName = ref('');
        const workflowChapterSelect = ref('');
        const workflowChapterBrief = ref('');
        const workflowF4aMode = ref('worldview');
        const workflowF4aInput = ref('');
        const f4aWorldview = ref({
            worldview: '', power_system: '', type: '', heroines: '',
            cheat: '', characters: '', factions: '', history: '', resources: '', others: ''
        });
        const f4aChar = ref({
            name: '', char_type: '男主角', char_shape: '圆形人物',
            identity: '', personality: '', appearance: '',
            ability: '', experience: '', attitude: ''
        });
        const projectCharacters = ref([]);

        const kbProject = ref('');
        const kbType = ref('settings');
        const kbItems = ref([]);
        const kbSelectedFile = ref('');
        const kbContent = ref('');

        const currentChat = computed(() => chats.value.find(c => c.id === currentChatId.value));
        
        const forbiddenRegex = computed(() => {
            const globalWords = config.value.globalForbidden.split(/[,，、\n\s]+/).map(w => w.trim()).filter(Boolean);
            const localWords = (currentChat.value?.localForbidden || '').split(/[,，、\n\s]+/).map(w => w.trim()).filter(Boolean);
            const allWords = [...new Set([...globalWords, ...localWords])];
            if (allWords.length === 0) return null;
            return new RegExp(`(${allWords.join('|')})`, 'gi');
        });

        watch(() => config.value.apiKey, val => localStorage.setItem('deepseekApiKey', val));
        
        // 会话管理
        const createNewChat = () => {
            const newId = 'chat_' + Date.now();
            chats.value.unshift(getNewChatTemplate(newId, '新计算进程'));
            currentChatId.value = newId;
        };
        const copyCurrentChat = () => {
            if(!currentChat.value) return;
            const newId = 'chat_' + Date.now();
            const copy = JSON.parse(JSON.stringify(currentChat.value));
            copy.id = newId;
            copy.title += ' (复刻)';
            chats.value.unshift(copy);
            currentChatId.value = newId;
        };
        const clearCurrentChatMessages = () => {
            if (currentChat.value) {
                currentChat.value.messages = [];
                currentChat.value.stats.total_tokens = 0;
                currentChat.value.stats.local_hit_count = 0;
            }
        };

        const scrollToBottom = () => {
            setTimeout(() => {
                const el = document.getElementById('chatContainer');
                if(el) el.scrollTop = el.scrollHeight;
            }, 50);
        };

        const stopGeneration = () => {
            if (abortController) {
                abortController.abort();
                isGenerating.value = false;
            }
        };

        // 发送指令及流式接收处理
        const sendMessage = async () => {
            if(!chatInput.value.trim() || isGenerating.value || !currentChat.value) return;
            if(!config.value.apiKey) { alert('系统阻断：未配置有效 API 凭证。'); return; }

            const userText = chatInput.value.trim();
            currentChat.value.messages.push({ role: 'user', content: userText });
            chatInput.value = '';
            scrollToBottom();

            const aiMessage = { 
                role: 'assistant', 
                versions: [{ content: '' }], 
                active_version: 0 
            };
            
            currentChat.value.messages.push(aiMessage);
            isGenerating.value = true;
            abortController = new AbortController();

            const apiMessages = currentChat.value.messages.slice(0, -1).map(m => ({
                role: m.role,
                content: m.role === 'user' ? m.content : m.versions[m.active_version].content
            }));

            try {
                const payload = {
                    api_key: config.value.apiKey,
                    model: currentChat.value.model,
                    messages: apiMessages,
                    system_prompt: currentChat.value.systemPrompt,
                    temperature: currentChat.value.temperature,
                    top_p: currentChat.value.top_p
                };

                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: abortController.signal
                });

                if (!response.ok) throw new Error("API 请求反馈异常状态");

                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    let chunk = decoder.decode(value, { stream: true });
                    
                    const usageMatch = chunk.match(/__USAGE__:(\d+),(\d+)__/);
                    if (usageMatch) {
                        currentChat.value.stats.total_tokens = (currentChat.value.stats.total_tokens || 0) + parseInt(usageMatch[1]) + parseInt(usageMatch[2]);
                        chunk = chunk.replace(/__USAGE__:\d+,\d+__/, '');
                    }

                    aiMessage.versions[aiMessage.active_version].content += chunk;
                    
                    const currentContent = aiMessage.versions[aiMessage.active_version].content;
                    if (forbiddenRegex.value && currentContent.length > 0) {
                        let matchCount = 0;
                        for (let i = 0; i < currentContent.length; i += 1000) {
                            const block = currentContent.slice(i, i + 1000);
                            const matches = block.match(forbiddenRegex.value);
                            if (matches) matchCount += matches.length;
                        }
                        
                        currentChat.value.stats.local_hit_count = matchCount;
                        
                        if (matchCount >= config.value.forbiddenTolerance) {
                            stopGeneration();
                            aiMessage.versions[aiMessage.active_version].content += '\n\n<div class="p-3 bg-red-100 text-red-700 rounded border border-red-300 mt-2 font-bold"><i class="fa-solid fa-triangle-exclamation"></i> 🛑 内容触发安全拦截机制：敏感词命中次数 (' + matchCount + ') 已达上限。</div>';
                            break;
                        }
                    }

                    scrollToBottom();
                }
            } catch (error) {
                if (error.name !== 'AbortError') {
                    aiMessage.versions[aiMessage.active_version].content += `\n\n[系统异常抛出: ${error.message}]`;
                }
            } finally {
                isGenerating.value = false;
            }
        };

        const renderMarkdown = (text) => {
            if (!text) return '';
            let parsed = marked.parse(text);
            if (forbiddenRegex.value) {
                parsed = parsed.replace(forbiddenRegex.value, '<span class="forbidden-highlight">$1</span>');
            }
            return parsed;
        };

        const loadProjects = async () => {
            const res = await fetch('/api/projects');
            projects.value = await res.json();
            if(projects.value.length && !currentProject.value) {
                currentProject.value = projects.value[0];
                fetchChapters();
                fetchProjectCharacters();
            }
        };
        const fetchChapters = async () => {
            if(!currentProject.value) return;
            const res = await fetch(`/api/projects/${currentProject.value}/chapters`);
            chapters.value = await res.json();
            if(chapters.value.length) {
                currentChapter.value = chapters.value[0];
                fetchContent();
            } else { currentChapter.value = ''; editorContent.value = ''; }
        };
        const fetchProjectCharacters = async () => {
            if(!currentProject.value) return;
            try {
                const res = await fetch(`/api/projects/${currentProject.value}/characters`);
                projectCharacters.value = await res.json();
            } catch(e) { console.error(e); }
        };
        const fetchContent = async () => {
            if(!currentProject.value || !currentChapter.value) return;
            const res = await fetch(`/api/projects/${currentProject.value}/chapters/${currentChapter.value}/content`);
            const data = await res.json();
            editorContent.value = data.content;
            saveStatus.value = '已同步';
        };
        const debouncedSave = () => {
            saveStatus.value = '修改侦测中...';
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(async () => {
                if(!currentProject.value || !currentChapter.value) return;
                saveStatus.value = '执行落盘...';
                await fetch(`/api/projects/${currentProject.value}/chapters/${currentChapter.value}/content`, {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: editorContent.value })
                });
                saveStatus.value = '已保存';
            }, 1000);
        };
        const addChapter = async () => {
            const name = prompt("请输入预生成章节名称 (不需加后缀)：", "新章节");
            if(name && name.trim()) {
                await fetch(`/api/projects/${currentProject.value}/chapters/${name.trim()}`, { method: 'POST' });
                await fetchChapters();
                currentChapter.value = name.trim() + '.txt';
                fetchContent();
            }
        };
        const renameChapter = async () => {
            const oldName = currentChapter.value.replace('.txt', '');
            const name = prompt("覆写原章节名：", oldName);
            if(name && name.trim() && name !== oldName) {
                await fetch(`/api/projects/${currentProject.value}/chapters/${oldName}?new_name=${name.trim()}`, { method: 'POST' });
                await fetchChapters();
                currentChapter.value = name.trim() + '.txt';
            }
        };
        const importToNovel = async (text) => {
            if(!currentProject.value) return;
            try {
                await fetch(`/api/projects/${currentProject.value}/append`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: text })
                });
                if(activeTab.value === 'editor') fetchContent();
                alert('导入已执行。');
            } catch(e) { alert('数据流追加引发异常。'); }
        };

        const loadReferences = async () => {
            const res = await fetch('/api/references');
            references.value = await res.json();
        };
        const loadStyles = async () => {
            const res = await fetch('/api/styles');
            availableStyles.value = await res.json();
        };

        const handleFileUpload = (event) => {
            const file = event.target.files[0];
            if (file) {
                uploadFileName.value = file.name;
                uploadFileObj = file;
            }
        };
        const submitUpload = async () => {
            if (!uploadFileObj) return;
            const formData = new FormData();
            formData.append('file', uploadFileObj);
            try {
                const res = await fetch('/api/references/upload', {
                    method: 'POST',
                    body: formData
                });
                if (res.ok) {
                    alert('参考文本上传成功');
                    uploadFileName.value = '';
                    uploadFileObj = null;
                    if (fileInput.value) fileInput.value.value = ''; 
                    await loadReferences(); 
                    selectedReference.value = formData.get('file').name; 
                } else {
                    alert('文件上传失败，请检查后端运行状态。');
                }
            } catch(e) {
                alert('上传发生网络异常。');
            }
        };
        
        // ============== 核心逻辑：一键自动文风提取流水线 ==============
        const waitForTask = (taskId) => {
            return new Promise((resolve, reject) => {
                const check = async () => {
                    try {
                        const res = await fetch(`/api/tasks/${taskId}`);
                        if (res.ok) {
                            const task = await res.json();
                            if (task.status === 'success') {
                                resolve(task);
                            } else if (task.status === 'failed' || task.status === 'error') {
                                reject(new Error(task.error || task.stderr || '任务执行失败'));
                            } else {
                                setTimeout(check, 2000); // 未完成则继续轮询
                            }
                        } else {
                            reject(new Error('无法获取任务状态'));
                        }
                    } catch (e) {
                        setTimeout(check, 2000);
                    }
                };
                check();
            });
        };

        const runStyleScriptAuto = async () => {
            if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
            
            // 解析输入的角色名列表 (兼容中英逗号)，如果留空则过滤后为空数组，直接跳过f3c
            const chars = autoStyleCharNames.value.split(/[,，]/).map(c => c.trim()).filter(Boolean);
            
            isAutoRunning.value = true;
            
            // 构建按顺序执行的脚本步骤队列
            let steps = [
                { script: 'f0', name: '全局基础RAG库初始化' },
                { script: 'f1a', name: '本地物理指标与TTR统计' },
                { script: 'f1b', name: '大模型深层文风提取' },
                { script: 'f2a', name: '本地高频词提取' },
                { script: 'f2b', name: '大模型词汇清洗分类' }
            ];
            
            // 如果是同人模式，继续追加设定和角色提取；如果是模仿模式则跳过
            if (autoPipelineType.value === 'fanfic') {
                steps.push({ script: 'f3a', name: '专属词库提取' });
                steps.push({ script: 'f3b', name: '世界观整理' });
                
                // 如果有角色，循环挂载f3c任务
                for (const char of chars) {
                    steps.push({ script: 'f3c', name: `角色卡提取 (${char})`, character: char });
                }
                
                steps.push({ script: 'f4b', name: '剧情动态压缩建库' });
            }

            try {
                for (const step of steps) {
                    autoRunProgress.value = `${step.script} - ${step.name}`;
                    
                    let url = `/api/scripts/${step.script}?target_file=${selectedReference.value}`;
                    
                    // 指定模型传参
                    if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(step.script)) {
                        url += `&model=${workflowStyleModel.value}`;
                    }
                    
                    // 角色参数
                    if (step.script === 'f3c') {
                        url += `&character=${step.character}`;
                    }
                    
                    // 发起任务
                    const res = await fetch(url, { method: 'POST' });
                    if (!res.ok) throw new Error(`${step.script} 请求失败`);
                    
                    const data = await res.json();
                    if (data.error) throw new Error(data.error);
                    
                    // 队列阻塞：一直等待该任务成功后才继续循环下一个
                    if (data.task_id) {
                        await waitForTask(data.task_id);
                    }
                    await pollTasks(); // 立刻刷新左边队列UI
                }
                alert("✅ 一键文风提取与仿写数据流构建：全自动流水线全部执行完成！");
            } catch (e) {
                alert(`❌ 流水线执行中断或遇到错误: ${e.message}`);
            } finally {
                isAutoRunning.value = false;
                autoRunProgress.value = '';
            }
        };
        // ==========================================================

        const runProjectScript = async () => {
            if (!currentProject.value) { alert("请先选择一个工程项目。"); return; }
            
            if (workflowProjectScript.value === 'f5a') {
                if (!workflowChapterName.value || !workflowChapterBrief.value) {
                    alert("请完善章节名及剧情简述信息。"); return;
                }
                await fetch('/api/scripts/f5a_outline', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        project_name: currentProject.value, 
                        chapter_name: workflowChapterName.value, 
                        chapter_brief: workflowChapterBrief.value,
                        model: workflowProjectModel.value
                    })
                });
                await pollTasks();
                return;
            }

            if (workflowProjectScript.value === 'f4a') {
                let formData = {};
                if (workflowF4aMode.value === 'worldview') {
                    if (!f4aWorldview.value.worldview || !f4aWorldview.value.power_system) { 
                        alert("世界观和力量体系为必填项"); return; 
                    }
                    formData = { 
                        worldview: f4aWorldview.value.worldview,
                        power_system: f4aWorldview.value.power_system,
                        type: f4aWorldview.value.type || "未定义", 
                        heroines: f4aWorldview.value.heroines || "未定义", 
                        cheat: f4aWorldview.value.cheat || "未定义",
                        characters: f4aWorldview.value.characters || "未定义", 
                        factions: f4aWorldview.value.factions || "未定义", 
                        history: f4aWorldview.value.history || "未定义", 
                        resources: f4aWorldview.value.resources || "未定义", 
                        others: f4aWorldview.value.others || ""
                    };
                } else {
                    if (!f4aChar.value.name || !f4aChar.value.char_type) {
                        alert("角色名和类型为必填项"); return;
                    }
                    formData = {
                        name: f4aChar.value.name,
                        char_type: f4aChar.value.char_type,
                        char_shape: f4aChar.value.char_shape,
                        identity: f4aChar.value.identity || "未定义",
                        personality: f4aChar.value.personality || "未定义",
                        appearance: f4aChar.value.appearance || "未定义",
                        ability: f4aChar.value.ability || "未定义", 
                        experience: f4aChar.value.experience || "未定义", 
                        attitude: f4aChar.value.attitude || "未定义"
                    };
                }

                await fetch('/api/scripts/f4a_completion', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        target_file: currentProject.value.replace('_style_imitation', ''),
                        mode: workflowF4aMode.value,
                        form_data: formData,
                        model: workflowProjectModel.value,
                        project_name: currentProject.value
                    })
                });
                await pollTasks();
                return;
            }

            if (workflowProjectScript.value === 'f5b') {
                if (!workflowChapterName.value) {
                    alert("请指定章节名。"); return;
                }
                fetch('/api/scripts/f5b_generate', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        project_name: currentProject.value, 
                        chapter_name: workflowChapterName.value,
                        model: workflowProjectModel.value
                    })
                }).then(() => pollTasks());
                setTimeout(pollTasks, 500);
                return;
            }

            let url = `/api/scripts/${workflowProjectScript.value}?project_name=${currentProject.value}`;
            url += `&model=${workflowProjectModel.value}`;
            
            if (['f5a', 'f5b', 'f7'].includes(workflowProjectScript.value)) {
                 if (!workflowChapterName.value.trim()) { alert("需指明目标章节名。"); return; }
                 url += `&chapter_name=${workflowChapterName.value.trim()}`;
            }
            
            await fetch(url, { method: 'POST' });
            await pollTasks();
        };

        const runStyleScript = async () => {
            if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
            
            // 👈 新增 &force=true，告诉后台我是单步点击的，不准跳过！ 
            let url = `/api/scripts/${workflowStyleScript.value}?target_file=${selectedReference.value}&force=true`;
            if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(workflowStyleScript.value)) {
                url += `&model=${workflowStyleModel.value}`;
            }

            if (workflowStyleScript.value === 'f3c') {
                if (!workflowCharName.value.trim()) { alert("需指明目标角色名参数。"); return; }
                url += `&character=${workflowCharName.value.trim()}`;
            }
            
            await fetch(url, { method: 'POST' });
            await pollTasks();
        };

        const createProject = async () => {
            const targetName = projectActionMode.value === 'create' ? newProjectName.value : existingProjectSelect.value;
            await fetch('/api/projects', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    name: targetName,
                    branch: newProjectBranch.value,
                    reference_style: newProjectReferenceStyle.value
                })
            });
            newProjectName.value = '';
            alert('底层工程目录及配置文件建立或覆盖完毕。');
            await loadProjects();
            // 选中新创建或被覆盖的项目
            currentProject.value = projects.value.find(p => p.startsWith(targetName)) || projects.value[projects.value.length - 1];
            activeTab.value = 'editor';
        };

        // 知识库文件交互 
        const fetchKbFilesList = async () => {
            kbSelectedFile.value = '';
            kbContent.value = '';
            kbItems.value = [];
            if (!kbProject.value) return;

            if (kbType.value === 'settings') {
                kbItems.value = [
                    { label: '文风特征设定 (features.md)', value: 'features.md' },
                    { label: '世界观设定 (world_settings.md)', value: 'world_settings.md' },
                    { label: '正面词库 (positive_words.md)', value: 'positive_words.md' },
                    { label: '负面词库 (negative_words.md)', value: 'negative_words.md' },
                    { label: '专属词库 (exclusive_vocab.md)', value: 'exclusive_vocab.md' },
                    { label: '剧情大纲 (plot_outlines.md)', value: 'plot_outlines.md' }
                ];
            } else if (kbType.value === 'characters') {
                try {
                    const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/characters`);
                    const list = await res.json();
                    kbItems.value = list.map(c => ({ label: c, value: c + '.md' }));
                } catch(e) { console.error(e); }
            } else if (kbType.value === 'outlines') {
                try {
                    const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/outlines`);
                    const list = await res.json();
                    kbItems.value = list.map(c => ({ label: c, value: c }));
                } catch(e) { console.error(e); }
            }
        };

        const fetchKbContent = async () => {
            if (!kbProject.value || !kbSelectedFile.value) return;
            let filePath = kbSelectedFile.value;
            if (kbType.value === 'characters') filePath = `character_profiles/${kbSelectedFile.value}`;
            else if (kbType.value === 'outlines') filePath = `chapter_structures/${kbSelectedFile.value}`;

            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`);
                if (res.ok) {
                    const data = await res.json();
                    kbContent.value = data.content;
                } else {
                    kbContent.value = "无法加载数据或文件尚不存在。";
                }
            } catch (e) {
                kbContent.value = "文件读取拦截，请检查环境服务接口配置。";
            }
        };

        const saveKbContent = async () => {
            if (!kbProject.value || !kbSelectedFile.value) return;
            let filePath = kbSelectedFile.value;
            if (kbType.value === 'characters') filePath = `character_profiles/${kbSelectedFile.value}`;
            else if (kbType.value === 'outlines') filePath = `chapter_structures/${kbSelectedFile.value}`;

            try {
                await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: kbContent.value })
                });
                alert("数据节点已物理落盘。");
            } catch (e) {
                alert("执行覆写操作失败。");
            }
        };

        onMounted(() => { loadProjects(); loadReferences(); loadStyles(); });

        return {
            config, chats, currentChatId, currentChat, chatInput, isGenerating,
            activeTab, projects, currentProject, chapters, currentChapter, editorContent, saveStatus,
            references, selectedReference, projectActionMode, newProjectName, existingProjectSelect, workflowCharName,
            kbProject, kbSelectedFile, kbContent, taskList, showAllTasks, visibleTasks, kbType, kbItems,
            createNewChat, copyCurrentChat, clearCurrentChatMessages, sendMessage, stopGeneration, renderMarkdown,
            fetchChapters, fetchContent, debouncedSave, addChapter, renameChapter, importToNovel,
            runProjectScript, runStyleScript, createProject, fetchKbFilesList, fetchKbContent, saveKbContent,
            workflowProjectModel, workflowStyleModel, workflowProjectScript, workflowStyleScript, newProjectBranch, newProjectReferenceStyle, availableStyles,
            workflowChapterName, workflowChapterSelect, workflowChapterBrief, workflowF4aMode, workflowF4aInput, projectCharacters, workflowCharSelect, f4aChar, f4aWorldview,
            fileInput, uploadFileName, handleFileUpload, submitUpload, loadReferences,
            
            // 导出一键流水线绑定的变量和方法
            styleExtractMode, autoPipelineType, autoStyleCharNames, isAutoRunning, autoRunProgress, runStyleScriptAuto
        };
    }
}).mount('#app');