const { ref, computed, watch } = Vue;

export function useWorkflow(projectModule) {
    const references = ref([]);
    const selectedReference = ref('');
    
    const styleExtractMode = ref('auto');
    const forceOverwrite = ref(false); 
    const autoPipelineType = ref('fanfic');
    const autoStyleCharNames = ref('');
    const isAutoRunning = ref(false);
    const autoRunProgress = ref('');
    const isAutoPaused = ref(false); 
    const cancelAutoFlag = ref(false); 
    
    const globalAutoValidate = ref(false);
    const globalAutoMemory = ref(false);
    
    const fileInput = ref(null);
    const uploadFileName = ref('');
    let uploadFileObj = null;

    const taskList = ref([]);
    const showAllTasks = ref(false);
    const visibleTasks = computed(() => showAllTasks.value ? taskList.value : taskList.value.slice(0, 5));

    const workflowProjectScript = ref('f5b');
    const workflowProjectModel = ref('deepseek-chat');
    const workflowStyleScript = ref('f1a');
    const workflowStyleModel = ref('deepseek-chat');

    const recommendedChars = ref([]);
    const freqChars = ref([]);
    const customCharInput = ref('');
    const showCharSelector = ref(false);
    const isLoadingChars = ref(false);

    const workflowCharName = ref('');
    const workflowCharSelect = ref('');
    const workflowChapterName = ref('');
    const workflowChapterSelect = ref('');
    const workflowChapterBrief = ref('');
    const workflowF4aMode = ref('worldview');
    const workflowF4aInput = ref('');
    const f4aWorldview = ref({ worldview: '', power_system: '', type: '', heroines: '', cheat: '', characters: '', factions: '', history: '', resources: '', others: '' });
    const f4aChar = ref({ name: '', char_type: '男主角', char_shape: '圆形人物', identity: '', personality: '', appearance: '', ability: '', experience: '', attitude: '' });
    const projectCharacters = ref([]);

    const kbProject = ref('');
    const kbType = ref('settings');
    const kbItems = ref([]);
    const kbSelectedFile = ref('');
    const kbContent = ref('');

    const pollTasks = async () => {
        try {
            const res = await fetch('/api/tasks');
            if(res.ok) taskList.value = await res.json();
        } catch(e) { console.error("轮询任务失败", e); }
    };
    setInterval(pollTasks, 2000);

    const loadReferences = async () => {
        const res = await fetch('/api/references');
        references.value = await res.json();
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
            const res = await fetch('/api/references/upload', { method: 'POST', body: formData });
            if (res.ok) {
                alert('参考文本上传成功');
                uploadFileName.value = ''; uploadFileObj = null;
                if (fileInput.value) fileInput.value.value = ''; 
                await loadReferences(); 
                selectedReference.value = formData.get('file').name; 
            } else {
                const errData = await res.json().catch(() => ({}));
                alert(`文件上传失败: ${errData.detail || errData.error || '后端异常'}`);
            }
        } catch(e) { alert('上传发生网络异常。'); }
    };

    const loadCharacterSuggestions = async () => {
        if (!selectedReference.value) { alert("请先在上方选择参考书！"); return; }
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
                const contentStr = wsData.content || "";
                
                const charsSectionMatch = contentStr.match(/角色.*?[：:]\s*([\s\S]*?)(?=\n[^\n]+[：:]|\n#|$)/);
                
                if (charsSectionMatch && charsSectionMatch[1]) {
                    const rawItems = charsSectionMatch[1].split(/[\n,，、;；]/);
                    rawItems.forEach(item => {
                        let cleanStr = item.replace(/^[\s\*\-\+>・]+/, '').trim();
                        if (!cleanStr) return;

                        let name = cleanStr;
                        let aliases = '';
                        const aliasMatch = cleanStr.match(/(.+?)[(（](.+?)[)）]/);
                        if (aliasMatch) { 
                            name = aliasMatch[1].trim(); 
                            aliases = aliasMatch[2].trim(); 
                        }
                        if (name.length > 0 && !recommendedChars.value.find(rc => rc.name === name)) {
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
                    const word = m[1], freq = parseInt(m[2]);
                    if (word.length >= 2 && !recommendedChars.value.find(rc => rc.name === word)) {
                        freqChars.value.push({ name: word, freq, selected: false });
                        count++;
                    }
                    if (count >= 40) break;
                }
            }
        } catch (e) {
            console.error("加载角色失败", e);
        } finally { isLoadingChars.value = false; }
    };

    const syncCharSelection = () => {
        const chars = [];
        recommendedChars.value.filter(c => c.selected).forEach(c => {
            chars.push(c.aliases ? `${c.name}(${c.aliases})` : c.name);
        });
        freqChars.value.filter(c => c.selected).forEach(c => chars.push(c.name));
        if (customCharInput.value.trim()) {
            const customs = customCharInput.value.split(/[,，]/).map(c => c.trim()).filter(Boolean);
            chars.push(...customs);
        }
        workflowCharName.value = chars.join(', ');
    };

    watch([recommendedChars, freqChars, customCharInput], syncCharSelection, { deep: true });

    const stopAutoPipeline = () => {
        if (isAutoRunning.value || isAutoPaused.value) {
            cancelAutoFlag.value = true;
            autoRunProgress.value = "正在强制终止流水线...";
            cancelLatestTask({ silent: true }).catch(() => {});
        }
    };

    const cancelLatestTask = async ({ silent = false } = {}) => {
        try {
            const res = await fetch('/api/task-actions/cancel_latest', { method: 'POST' });
            const data = await handleApiResponse(res);
            await pollTasks();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`终止最近任务失败: ${e.message}`);
            throw e;
        }
    };

    const cancelAllTasks = async ({ silent = false } = {}) => {
        try {
            const res = await fetch('/api/task-actions/cancel_all', { method: 'POST' });
            const data = await handleApiResponse(res);
            await pollTasks();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`终止全部任务失败: ${e.message}`);
            throw e;
        }
    };

    const waitForTask = (taskId) => { 
        return new Promise((resolve, reject) => { 
            const check = async () => { 
                if (cancelAutoFlag.value) return reject(new Error('用户手动终止了流水线')); 
                try { 
                    const res = await fetch(`/api/tasks/${taskId}`); 
                    if (res.ok) { 
                        const task = await res.json(); 
                        if (task.status === 'success') resolve(task); 
                        else if (task.status === 'cancelled') reject(new Error(task.error || '任务已取消')); 
                        else if (task.status === 'failed' || task.status === 'error') reject(new Error(task.error || task.stderr || '任务执行失败')); 
                        else setTimeout(check, 2000); 
                    } else if (res.status === 404) { 
                        reject(new Error('任务记录已被物理清理或进程已丢失。')); 
                    } else { 
                        setTimeout(check, 2000); 
                    } 
                } catch (e) { setTimeout(check, 2000); } 
            }; 
            check(); 
        }); 
    }; 

    // 核心安全修补：统一错误拦截器，防止 FastAPI detail 被静默吞噬
    const handleApiResponse = async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const errMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : (data.error || `HTTP 错误状态: ${res.status}`);
            throw new Error(errMsg);
        }
        if (data.error) throw new Error(data.error);
        return data;
    };

    const executePipelineStep = async (step, customChar = null) => {
        if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");
        autoRunProgress.value = `${step.script} - ${step.name}`;
        
        let url = `/api/scripts/${step.script}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(step.script)) {
            url += `&model=${workflowStyleModel.value}`;
        }
        if (step.script === 'f3c' && customChar) url += `&character=${encodeURIComponent(customChar)}`;
        
        const res = await fetch(url, { method: 'POST' });
        const data = await handleApiResponse(res);
        if (data.task_id) await waitForTask(data.task_id);
        await pollTasks();
    };

    const runStyleScriptAuto = async () => {
        if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
        isAutoRunning.value = true; isAutoPaused.value = false; cancelAutoFlag.value = false; 
        
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
            for (const step of stepsPhase1) await executePipelineStep(step);
            if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");

            if (autoPipelineType.value === 'fanfic') {
                autoRunProgress.value = "等待人工干预：点击获取角色并确认";
                isAutoPaused.value = true;
                alert("前置设定已提取完成！请在下方点击【获取推荐名单】。");
            } else {
                alert("模仿模式：基础文风提取流水线执行完成！");
                isAutoRunning.value = false; autoRunProgress.value = '';
            }
        } catch (e) {
            alert(e.message.includes('手动终止') ? "已成功终止流水线任务队列。" : `流水线中断: ${e.message}`);
            isAutoRunning.value = false; isAutoPaused.value = false; autoRunProgress.value = '';
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
            alert(e.message.includes('手动终止') ? "已成功终止任务队列。" : `后半段流水线中断: ${e.message}`);
        } finally {
            isAutoRunning.value = false; autoRunProgress.value = '';
        }
    };

    const runProjectScript = async () => {
        if (!projectModule.currentProject.value) { alert("请先选择一个工程项目。"); return; }
        
        const curProj = projectModule.currentProject.value;
        
        const triggerAutoMemory = async () => {
            if (!globalAutoMemory.value) return;
            try {
                let url = `/api/scripts/f4c?project_name=${encodeURIComponent(curProj)}&force=true`;
                const mRes = await fetch(url, { method: 'POST' });
                const mData = await handleApiResponse(mRes);
                if (mData.task_id) {
                    alert(`已自动触发 [f4c] 前文记忆库构建，请耐心等待全量向量化完成...`);
                    await waitForTask(mData.task_id);
                    alert(`【记忆构建完毕】最新正文上下文已入库，即将开始创作任务！`);
                }
            } catch (e) {
                alert(`前置记忆构建环节发生异常阻断: ${e.message}`);
                throw e; 
            }
        };

        const triggerAutoValidation = async (targetNode) => {
            if (!globalAutoValidate.value) return;
            try {
                let url = `/api/scripts/f7?project_name=${encodeURIComponent(curProj)}&model=${workflowProjectModel.value}&chapter_name=${encodeURIComponent(workflowChapterName.value.trim())}`;
                const vRes = await fetch(url, { method: 'POST' });
                const vData = await handleApiResponse(vRes);
                if (vData.task_id) {
                    alert(`已自动触发 [${targetNode}] 节点的 f7 文本校验，等待执行完成...`);
                    await waitForTask(vData.task_id);
                    alert(`【全局校验完毕】[${targetNode}] 生成与物理硬校验流水线已结束！`);
                }
            } catch (e) {
                alert(`自动校验环节发生异常阻断: ${e.message}`);
            }
        };
        
        if (workflowProjectScript.value === 'f4a') {
            const formData = workflowF4aMode.value === 'worldview' ? f4aWorldview.value : f4aChar.value;
            const payload = {
                project_name: curProj,
                mode: workflowF4aMode.value,
                target_file: selectedReference.value || "",
                model: workflowProjectModel.value,
                form_data: formData
            };
            
            try {
                const res = await fetch('/api/scripts/f4a_completion', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await handleApiResponse(res);
                if (data.task_id) {
                    alert(`设定补全任务已提交，请在左侧控制台查看进度！`);
                }
            } catch (e) {
                alert(`设定补全触发失败: ${e.message}`);
            }
            await pollTasks();
            return; 
        }

        if (workflowProjectScript.value === 'f5a') {
            if (!workflowChapterName.value || !workflowChapterBrief.value) { alert("请完善章节信息。"); return; }
            
            try {
                await triggerAutoMemory();

                const res = await fetch('/api/scripts/f5a_outline', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_name: curProj, chapter_name: workflowChapterName.value, chapter_brief: workflowChapterBrief.value, model: workflowProjectModel.value })
                });
                const data = await handleApiResponse(res);
                if (data.task_id) {
                    await waitForTask(data.task_id);
                    await triggerAutoValidation('f5a');
                }
            } catch (e) {
                alert(`大纲生成请求异常: ${e.message}`);
            }
            await pollTasks();
            return;
        }

        if (workflowProjectScript.value === 'f5b') {
            if (!workflowChapterName.value) { alert("请指定章节名。"); return; }
            
            try {
                await triggerAutoMemory();

                const res = await fetch('/api/scripts/f5b_generate', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_name: curProj, chapter_name: workflowChapterName.value, model: workflowProjectModel.value })
                });
                const data = await handleApiResponse(res);
                
                if (data.task_id) {
                    alert(`生成任务已提交，完成后将自动同步！${globalAutoValidate.value ? '(将在结束后连贯执行文本校验)' : ''}`);
                    await waitForTask(data.task_id); 
                    await projectModule.fetchChapters(); 
                    projectModule.currentChapter.value = workflowChapterName.value.replace('.txt', '') + '.txt';
                    await projectModule.fetchContent(); 
                    
                    if (globalAutoValidate.value) {
                        await triggerAutoValidation('f5b');
                    } else {
                        alert("章节正文生成完成！已同步显示在左侧编辑器中。");
                    }
                }
            } catch (e) {
                alert(`正文生成请求异常: ${e.message}`);
            }
            await pollTasks();
            return;
        }
        
        try {
            let url = `/api/scripts/${workflowProjectScript.value}?project_name=${encodeURIComponent(curProj)}&model=${workflowProjectModel.value}`;
            if (['f7'].includes(workflowProjectScript.value) && workflowChapterName.value) {
                 url += `&chapter_name=${encodeURIComponent(workflowChapterName.value.trim())}`;
            }
            const res = await fetch(url, { method: 'POST' });
            await handleApiResponse(res);
        } catch (e) {
            alert(`辅助脚本执行异常: ${e.message}`);
        }
        await pollTasks();
    };

    const runStyleScript = async () => {
        if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
        let url = `/api/scripts/${workflowStyleScript.value}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(workflowStyleScript.value)) url += `&model=${workflowStyleModel.value}`;
        if (workflowStyleScript.value === 'f3c') {
            if (!workflowCharName.value.trim()) { alert("需指明目标角色名参数。"); return; }
            url += `&character=${encodeURIComponent(workflowCharName.value.trim())}`;
        }
        
        try {
            const res = await fetch(url, { method: 'POST' });
            await handleApiResponse(res);
        } catch (e) {
            alert(`特征提取脚本执行异常: ${e.message}`);
        }
        await pollTasks();
    };

    const fetchKbFilesList = async () => {
        kbSelectedFile.value = ''; kbContent.value = ''; kbItems.value = [];
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
        } else {
            const endpoints = { 'characters': 'characters', 'outlines': 'outlines', 'prompts': 'prompts' };
            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/${endpoints[kbType.value]}`);
                const list = await res.json();
                kbItems.value = list.map(c => ({ label: c, value: kbType.value === 'characters' ? c + '.md' : c }));
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
            } else kbContent.value = "无法加载数据或文件尚不存在。";
        } catch (e) { kbContent.value = "文件读取拦截。"; }
    };

    const saveKbContent = async () => {
        if (!kbProject.value || !kbSelectedFile.value) return;
        let filePath = kbSelectedFile.value;
        if (kbType.value === 'characters') filePath = `character_profiles/${kbSelectedFile.value}`;
        else if (kbType.value === 'outlines') filePath = `chapter_structures/${kbSelectedFile.value}`;
        else if (kbType.value === 'prompts') filePath = `chapter_specific_prompts/${kbSelectedFile.value}`; 

        try {
            await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: kbContent.value })
            });
            alert("数据节点已物理落盘。");
        } catch (e) { alert("执行覆写操作失败。"); }
    };

    return {
        references, selectedReference, styleExtractMode, forceOverwrite, autoPipelineType, autoStyleCharNames,
        isAutoRunning, autoRunProgress, isAutoPaused, cancelAutoFlag, globalAutoValidate, globalAutoMemory, fileInput, uploadFileName, taskList, showAllTasks, visibleTasks,
        workflowProjectScript, workflowProjectModel, workflowStyleScript, workflowStyleModel,
        recommendedChars, freqChars, customCharInput, showCharSelector, isLoadingChars, workflowCharName, workflowCharSelect,
        workflowChapterName, workflowChapterSelect, workflowChapterBrief, workflowF4aMode, workflowF4aInput,
        f4aWorldview, f4aChar, projectCharacters, kbProject, kbType, kbItems, kbSelectedFile, kbContent,
        loadReferences, handleFileUpload, submitUpload, loadCharacterSuggestions, stopAutoPipeline, cancelLatestTask, cancelAllTasks, executePipelineStep,
        runStyleScriptAuto, continueAutoPipeline, runProjectScript, runStyleScript, fetchKbFilesList, fetchKbContent, saveKbContent
    };
}
