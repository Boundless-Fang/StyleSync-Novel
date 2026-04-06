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
        
        // 自动流水线模式参数
        const styleExtractMode = ref('auto');
        const forceOverwrite = ref(false); // 新增：全局强制覆盖开关
        const autoPipelineType = ref('fanfic');
        const autoStyleCharNames = ref('');
        const isAutoRunning = ref(false);
        const autoRunProgress = ref('');
        const isAutoPaused = ref(false); 
        const cancelAutoFlag = ref(false); 
        
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

        const projectActionMode = ref('create'); 
        const newProjectName = ref('');
        const existingProjectSelect = ref('');
        const newProjectBranch = ref('原创');
        const newProjectReferenceStyle = ref('');
        const availableStyles = ref([]);
        
        const workflowProjectScript = ref('f5b');
        const workflowProjectModel = ref('deepseek-chat');
        
        const workflowStyleScript = ref('f1a');
        const workflowStyleModel = ref('deepseek-chat');

        // ================= f3c 角色选择器面板专属变量 ================= 
        const recommendedChars = ref([]);
        const freqChars = ref([]);
        const customCharInput = ref('');
        const showCharSelector = ref(false);
        const isLoadingChars = ref(false);

        const loadCharacterSuggestions = async () => {
            if (!selectedReference.value) {
                alert("请先在上方选择参考书！");
                return;
            }
            isLoadingChars.value = true;
            showCharSelector.value = true;
            recommendedChars.value = [];
            freqChars.value = [];

            const styleName = selectedReference.value.replace(/\.txt$/i, '') + '_style_imitation';
            const fakeProjName = encodeURIComponent('style@@' + styleName);

            try {
                const wsRes = await fetch(`/api/projects/${fakeProjName}/settings/world_settings.md`);
                if (wsRes.ok) {
                    const wsData = await wsRes.json();
                    const match = (wsData.content || "").match(/角色.*?[：:]\s*(.*)/);
                    if (match && match[1]) {
                        const rawChars = match[1].split(/[,，、]/).map(c => c.trim()).filter(Boolean);
                        rawChars.forEach(c => {
                            let name = c;
                            let aliases = '';
                            const aliasMatch = c.match(/(.+?)[(（](.+?)[)）]/);
                            if (aliasMatch) {
                                name = aliasMatch[1].trim();
                                aliases = aliasMatch[2].trim();
                            }
                            if (!recommendedChars.value.find(rc => rc.name === name)) {
                                recommendedChars.value.push({ name, aliases, selected: true, editing: false });
                            }
                        });
                    }
                }

                const freqRes = await fetch(`/api/projects/${fakeProjName}/settings/statistics/高频词.txt`);
                if (freqRes.ok) {
                    const freqData = await freqRes.json();
                    const matches = [...(freqData.content || "").matchAll(/(\S+)\((\d+)\)/g)];
                    let count = 0;
                    for (const m of matches) {
                        const word = m[1];
                        const freq = parseInt(m[2]);
                        if (word.length >= 2 && !recommendedChars.value.find(rc => rc.name === word)) {
                            freqChars.value.push({ name: word, freq, selected: false });
                            count++;
                        }
                        if (count >= 40) break;
                    }
                }
            } catch (e) {
                console.error("加载角色失败", e);
            } finally {
                isLoadingChars.value = false;
            }
        };

        const syncCharSelection = () => {
            const chars = [];
            recommendedChars.value.filter(c => c.selected).forEach(c => {
                chars.push(c.aliases ? `${c.name}(${c.aliases})` : c.name);
            });
            freqChars.value.filter(c => c.selected).forEach(c => {
                chars.push(c.name);
            });
            if (customCharInput.value.trim()) {
                const customs = customCharInput.value.split(/[,，]/).map(c => c.trim()).filter(Boolean);
                chars.push(...customs);
            }
            workflowCharName.value = chars.join(', ');
        };

        watch([recommendedChars, freqChars, customCharInput], syncCharSelection, { deep: true });
        // ============================================================== 

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
                            aiMessage.versions[aiMessage.active_version].content += '\n\n<div class="p-3 bg-red-100 text-red-700 rounded border border-red-300 mt-2 font-bold"><i class="fa-solid fa-triangle-exclamation"></i> 内容触发安全拦截机制：敏感词命中次数 (' + matchCount + ') 已达上限。</div>';
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
            
            // 1. 将 Markdown 解析为 HTML
            let parsedHtml = marked.parse(text);
            
            // 2. 【核心修复】：使用 DOMPurify 清洗危险标签 (防 XSS 注入)
            parsedHtml = DOMPurify.sanitize(parsedHtml);
            
            // 3. 处理敏感词高亮
            if (forbiddenRegex.value) {
                parsedHtml = parsedHtml.replace(forbiddenRegex.value, '<span class="forbidden-highlight">$1</span>');
            }
            
            return parsedHtml;
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
        // ======= 新建章节弹窗状态与逻辑 ======= 
        const showChapterModal = ref(false); 
        const newChapterNum = ref(1); 
        const newChapterTitle = ref(''); 

        const getChapterNumber = (name) => { 
            let arabicMatch = name.match(/\d+/); 
            if (arabicMatch) return parseInt(arabicMatch[0]); 
  
            let cnMatch = name.match(/第([零一二两三四五六七八九十百千万]+)[章回节卷]/); 
            if (cnMatch) { 
                const cnNum = cnMatch[1]; 
                const cnMap = { '零':0, '一':1, '二':2, '两':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9 }; 
                const cnUnits = { '十':10, '百':100, '千':1000, '万':10000 }; 
                 
                let result = 0; 
                let tmp = 0; 
                for (let i = 0; i < cnNum.length; i++) { 
                    let char = cnNum[i]; 
                    if (cnUnits[char]) { 
                        let unit = cnUnits[char]; 
                        if (tmp === 0 && unit === 10) tmp = 1; 
                        result += tmp * unit; 
                        tmp = 0; 
                    } else { 
                        tmp = cnMap[char] || 0; 
                    } 
                } 
                result += tmp; 
                return result; 
            } 
            return 999999; 
        }; 

        const fetchChapters = async () => { 
            if(!currentProject.value) return; 
            const res = await fetch(`/api/projects/${currentProject.value}/chapters`); 
            let rawChapters = await res.json(); 
            
            rawChapters.sort((a, b) => getChapterNumber(a) - getChapterNumber(b)); 
            chapters.value = rawChapters; 
            
            if(chapters.value.length) { 
                if (!currentChapter.value || !chapters.value.includes(currentChapter.value)) { 
                    currentChapter.value = chapters.value[chapters.value.length - 1]; 
                } 
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
            const cleanName = currentChapter.value.replace('.txt', ''); 
            const res = await fetch(`/api/projects/${currentProject.value}/chapters/${cleanName}/content`); 
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
                const cleanName = currentChapter.value.replace('.txt', ''); 
                await fetch(`/api/projects/${currentProject.value}/chapters/${cleanName}/content`, { 
                    method: 'PUT', headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify({ content: editorContent.value }) 
                }); 
                saveStatus.value = '已保存'; 
            }, 1000); 
        }; 

        const openCreateModal = () => { 
            if (!currentProject.value) { 
                alert("请先选择一个目标项目。"); 
                return; 
            } 
            let maxNum = 0; 
            chapters.value.forEach(c => { 
                let num = getChapterNumber(c); 
                if(num !== 9999 && num !== 999 && num > maxNum) maxNum = num; 
            }); 
            newChapterNum.value = maxNum + 1; 
            newChapterTitle.value = ''; 
            showChapterModal.value = true; 
        }; 

        const confirmCreateChapter = async () => { 
            let finalName = `第${newChapterNum.value}章`; 
            if (newChapterTitle.value.trim()) { 
                finalName += `_${newChapterTitle.value.trim()}`; 
            } 

            try { 
                const res = await fetch(`/api/projects/${currentProject.value}/chapters/${finalName}`, { method: 'POST' }); 
                if (res.ok) { 
                    await fetchChapters(); 
                    currentChapter.value = finalName + '.txt'; 
                    workflowChapterSelect.value = finalName; 
                    workflowChapterName.value = finalName; 
                    showChapterModal.value = false; 
                } else { 
                    alert("创建失败，请检查后端状态。"); 
                } 
            } catch (e) { 
                alert(`请求异常: ${e.message}`); 
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

        // 工作流专用：新建空白章节
        const addChapterFromWorkflow = async () => {
            if (!currentProject.value) {
                alert("请先选择一个目标项目。");
                return;
            }
            
            let name = workflowChapterName.value.trim();
            if (!name) {
                name = prompt("请输入预生成章节名称 (不需加后缀)：", "新章节");
                if (!name || !name.trim()) return;
                name = name.trim();
            }

            try {
                const res = await fetch(`/api/projects/${currentProject.value}/chapters/${name}`, { method: 'POST' });
                if (res.ok) {
                    await fetchChapters();
                    workflowChapterSelect.value = name;
                    workflowChapterName.value = name;
                    alert(`章节 [${name}] 已在底层创建成功！`);
                } else {
                    alert("创建失败，请检查后端状态。");
                }
            } catch (e) {
                alert(`请求异常: ${e.message}`);
            }
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
        
        const stopAutoPipeline = () => {
            if (isAutoRunning.value || isAutoPaused.value) {
                cancelAutoFlag.value = true;
                autoRunProgress.value = "正在强制终止流水线，等待当前步骤结束...";
            }
        };

        const waitForTask = (taskId) =>  { 
            return new Promise((resolve, reject) =>  { 
                const check = async  () => { 
                    if  (cancelAutoFlag.value) { 
                        reject(new Error('用户手动终止了流水线' )); 
                        return ; 
                    } 
                    try  { 
                        const res = await fetch(`/api/tasks/${taskId}` ); 
                        if  (res.ok) { 
                            const task = await  res.json(); 
                            if (task.status === 'success' ) { 
                                resolve(task); 
                            } else if (task.status === 'failed' || task.status === 'error' ) { 
                                reject(new Error(task.error || task.stderr || '任务执行失败' )); 
                            } else  { 
                                setTimeout(check, 2000 ); 
                            } 
                        } else if (res.status === 404 ) { 
                            // 防线五：精准捕获后端淘汰清理信号，斩断死循环 
                            reject(new Error('系统拦截：任务记录已被物理清理或进程已丢失。' )); 
                        } else  { 
                            // 兼容 502/504 等网络波动 
                            setTimeout(check, 2000 ); 
                        } 
                    } catch  (e) { 
                        setTimeout(check, 2000 ); 
                    } 
                }; 
                check(); 
            }); 
        }; 

        const executePipelineStep = async (step, customChar = null) => {
            if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");
            autoRunProgress.value = `${step.script} - ${step.name}`;
            
            let url = `/api/scripts/${step.script}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
            
            if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(step.script)) {
                url += `&model=${workflowStyleModel.value}`;
            }
            if (step.script === 'f3c' && customChar) {
                url += `&character=${encodeURIComponent(customChar)}`;
            }
            
            const res = await fetch(url, { method: 'POST' });
            if (!res.ok) throw new Error(`${step.script} 请求失败`);
            
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            
            if (data.task_id) {
                await waitForTask(data.task_id);
            }
            await pollTasks();
        };

        // 【还原修改】：原版优美的一键执行流水线逻辑
        const runStyleScriptAuto = async () => {
            if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
            
            isAutoRunning.value = true;
            isAutoPaused.value = false;
            cancelAutoFlag.value = false; 
            
            let stepsPhase1 = [
                { script: 'f0', name: '全局基础RAG库初始化' },
                { script: 'f1a', name: '本地物理指标与TTR统计' },
                { script: 'f1b', name: '大模型深层文风提取' },
                { script: 'f2a', name: '本地高频词提取' },
                { script: 'f2b', name: '大模型词汇清洗分类' }
            ];
            
            if (autoPipelineType.value === 'fanfic') {
                stepsPhase1.push({ script: 'f3a', name: '专属词库提取' });
                stepsPhase1.push({ script: 'f3b', name: '世界观整理' });
            }

            try {
                for (const step of stepsPhase1) {
                    await executePipelineStep(step);
                }
                
                if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");

                if (autoPipelineType.value === 'fanfic') {
                    // 只暂停，不再自动加载名单，等用户自己点按钮
                    autoRunProgress.value = "等待人工干预：点击获取角色并确认";
                    isAutoPaused.value = true;
                    alert("前置设定 (f0-f3b) 已提取完成！请在下方点击【获取推荐名单】按钮。");
                } else {
                    alert("模仿模式：基础文风提取流水线执行完成！");
                    isAutoRunning.value = false;
                    autoRunProgress.value = '';
                }
            } catch (e) {
                if (e.message.includes('手动终止')) {
                    alert("已成功终止流水线任务队列。");
                } else {
                    alert(`流水线执行中断或遇到错误: ${e.message}`);
                }
                isAutoRunning.value = false;
                isAutoPaused.value = false;
                autoRunProgress.value = '';
            }
        };

        const continueAutoPipeline = async () => {
            isAutoPaused.value = false;
            if (cancelAutoFlag.value) return; 

            const chars = workflowCharName.value.split(/[,，]/).map(c => c.trim()).filter(Boolean);
            
            try {
                for (const char of chars) {
                    await executePipelineStep({ script: 'f3c', name: `角色卡提取 (${char})` }, char);
                }
                await executePipelineStep({ script: 'f4b', name: '剧情动态压缩建库' });
                
                alert("同人模式：文风提取与仿写数据流构建全部执行完成！");
            } catch(e) {
                if (e.message.includes('手动终止')) {
                    alert("已成功终止流水线任务队列。");
                } else {
                    alert(`后半段流水线中断: ${e.message}`);
                }
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
                const res = await fetch('/api/scripts/f5a_outline', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        project_name: currentProject.value, 
                        chapter_name: workflowChapterName.value, 
                        chapter_brief: workflowChapterBrief.value,
                        model: workflowProjectModel.value
                    })
                });
                const data = await res.json();
                if (data.error) { alert("执行错误: " + data.error); return; }
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
                        worldview: f4aWorldview.value.worldview, power_system: f4aWorldview.value.power_system,
                        type: f4aWorldview.value.type || "未定义", heroines: f4aWorldview.value.heroines || "未定义", 
                        cheat: f4aWorldview.value.cheat || "未定义", characters: f4aWorldview.value.characters || "未定义", 
                        factions: f4aWorldview.value.factions || "未定义", history: f4aWorldview.value.history || "未定义", 
                        resources: f4aWorldview.value.resources || "未定义", others: f4aWorldview.value.others || ""
                    };
                } else {
                    if (!f4aChar.value.name || !f4aChar.value.char_type) {
                        alert("角色名和类型为必填项"); return;
                    }
                    formData = {
                        name: f4aChar.value.name, char_type: f4aChar.value.char_type, char_shape: f4aChar.value.char_shape,
                        identity: f4aChar.value.identity || "未定义", personality: f4aChar.value.personality || "未定义",
                        appearance: f4aChar.value.appearance || "未定义", ability: f4aChar.value.ability || "未定义", 
                        experience: f4aChar.value.experience || "未定义", attitude: f4aChar.value.attitude || "未定义"
                    };
                }

                const res = await fetch('/api/scripts/f4a_completion', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        target_file: currentProject.value.replace('_style_imitation', ''),
                        mode: workflowF4aMode.value,
                        form_data: formData,
                        model: workflowProjectModel.value,
                        project_name: currentProject.value
                    })
                });
                const data = await res.json();
                if (data.error) { alert("执行错误: " + data.error); return; }
                await pollTasks();
                return;
            }

            if (workflowProjectScript.value === 'f5b') {
                if (!workflowChapterName.value) {
                    alert("请指定章节名。"); return;
                }
                const res = await fetch('/api/scripts/f5b_generate', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        project_name: currentProject.value, 
                        chapter_name: workflowChapterName.value,
                        model: workflowProjectModel.value
                    })
                });
                const data = await res.json();
                if (data.error) { 
                    alert("执行错误: " + data.error); 
                    return; 
                }
                
                // 【核心修复3】：死等 f5b 写完，然后刷新编辑器
                if (data.task_id) {
                    alert("小说生成任务已提交后台执行，完成后将自动同步到编辑器！");
                    await waitForTask(data.task_id); 
                    
                    await fetchChapters(); 
                    currentChapter.value = workflowChapterName.value.replace('.txt', '') + '.txt';
                    await fetchContent(); 
                    alert("章节正文生成完成！已同步显示在左侧编辑器中。");
                }
                await pollTasks();
                return;
            }

            let url = `/api/scripts/${workflowProjectScript.value}?project_name=${encodeURIComponent(currentProject.value)}`;
            url += `&model=${workflowProjectModel.value}`;
            
            if (['f5a', 'f5b', 'f7'].includes(workflowProjectScript.value)) {
                 if (!workflowChapterName.value.trim()) { alert("需指明目标章节名。"); return; }
                 url += `&chapter_name=${encodeURIComponent(workflowChapterName.value.trim())}`;
            }
            
            await fetch(url, { method: 'POST' });
            await pollTasks();
        };

        const runStyleScript = async () => {
            if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
            
            let url = `/api/scripts/${workflowStyleScript.value}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
            if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(workflowStyleScript.value)) {
                url += `&model=${workflowStyleModel.value}`;
            }

            if (workflowStyleScript.value === 'f3c') {
                if (!workflowCharName.value.trim()) { alert("需指明目标角色名参数。"); return; }
                url += `&character=${encodeURIComponent(workflowCharName.value.trim())}`;
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
            } else if (kbType.value === 'prompts') {
                try {
                    const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/prompts`);
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
            else if (kbType.value === 'prompts') filePath = `chapter_specific_prompts/${kbSelectedFile.value}`; 

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
            else if (kbType.value === 'prompts') filePath = `chapter_specific_prompts/${kbSelectedFile.value}`; 

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
            fetchChapters, fetchContent, debouncedSave, renameChapter, importToNovel,
            runProjectScript, runStyleScript, createProject, fetchKbFilesList, fetchKbContent, saveKbContent,
            showChapterModal, newChapterNum, newChapterTitle, openCreateModal, confirmCreateChapter,
            workflowProjectModel, workflowStyleModel, workflowProjectScript, workflowStyleScript, newProjectBranch, newProjectReferenceStyle, availableStyles,
            workflowChapterName, workflowChapterSelect, workflowChapterBrief, workflowF4aMode, workflowF4aInput, projectCharacters, workflowCharSelect, f4aChar, f4aWorldview,
            fileInput, uploadFileName, handleFileUpload, submitUpload, loadReferences,
            
            recommendedChars, freqChars, customCharInput, showCharSelector, isLoadingChars, loadCharacterSuggestions,
            
            styleExtractMode, forceOverwrite, autoPipelineType, autoStyleCharNames, isAutoRunning, autoRunProgress,
            isAutoPaused, cancelAutoFlag, stopAutoPipeline, runStyleScriptAuto, continueAutoPipeline
        };
    }
}).mount('#app');