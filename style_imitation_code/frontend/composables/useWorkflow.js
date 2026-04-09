// composables/useWorkflow.js
const { ref, computed, watch, onMounted } = Vue;

export function useWorkflow(projectState) {
    // ================= 任务系统状态 =================
    const taskList = ref([]);
    const showAllTasks = ref(false);
    const visibleTasks = computed(() => showAllTasks.value ? taskList.value : taskList.value.slice(0, 5));

    // ================= 文件上传与解析状态 =================
    const references = ref([]);
    const selectedReference = ref('');
    const availableStyles = ref([]);
    const fileInput = ref(null);
    const uploadFileName = ref('');
    let uploadFileObj = null;

    // ================= 工作流表单状态 =================
    const projectActionMode = ref('create'); 
    const newProjectName = ref('');
    const existingProjectSelect = ref('');
    const newProjectBranch = ref('原创');
    const newProjectReferenceStyle = ref('');
    
    const workflowProjectScript = ref('f5b');
    const workflowProjectModel = ref('deepseek-chat');
    const workflowStyleScript = ref('f1a');
    const workflowStyleModel = ref('deepseek-chat');

    const workflowCharName = ref('');
    const workflowChapterName = ref('');
    const workflowChapterSelect = ref('');
    const workflowChapterBrief = ref('');
    const workflowF4aMode = ref('worldview');
    const f4aWorldview = ref({
        worldview: '', power_system: '', type: '', heroines: '',
        cheat: '', characters: '', factions: '', history: '', resources: '', others: ''
    });
    const f4aChar = ref({
        name: '', char_type: '男主角', char_shape: '圆形人物',
        identity: '', personality: '', appearance: '',
        ability: '', experience: '', attitude: ''
    });

    // ================= 弹窗与角色解析状态 =================
    const showChapterModal = ref(false); 
    const newChapterNum = ref(1); 
    const newChapterTitle = ref(''); 

    const recommendedChars = ref([]);
    const freqChars = ref([]);
    const customCharInput = ref('');
    const showCharSelector = ref(false);
    const isLoadingChars = ref(false);

    // ================= 一键流水线状态 =================
    const styleExtractMode = ref('auto');
    const forceOverwrite = ref(false);
    const autoPipelineType = ref('fanfic');
    const autoStyleCharNames = ref('');
    const isAutoRunning = ref(false);
    const autoRunProgress = ref('');
    const isAutoPaused = ref(false); 
    const cancelAutoFlag = ref(false); 

    // ================= 方法：任务与基础数据 =================
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
            const res = await fetch('/api/references/upload', { method: 'POST', body: formData });
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
        } catch(e) { alert('上传发生网络异常。'); }
    };

    // ================= 方法：工程创建与章节 =================
    const createProject = async () => {
        const targetName = projectActionMode.value === 'create' ? newProjectName.value : existingProjectSelect.value;
        await fetch('/api/projects', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                name: targetName, branch: newProjectBranch.value, reference_style: newProjectReferenceStyle.value
            })
        });
        newProjectName.value = '';
        alert('底层工程目录及配置文件建立或覆盖完毕。');
        await projectState.loadProjects();
        projectState.currentProject.value = projectState.projects.value.find(p => p.startsWith(targetName)) || projectState.projects.value[projectState.projects.value.length - 1];
        projectState.activeTab.value = 'editor';
    };

    const openCreateModal = () => { 
        if (!projectState.currentProject.value) { alert("请先选择一个目标项目。"); return; } 
        let maxNum = 0; 
        projectState.chapters.value.forEach(c => { 
            let num = projectState.getChapterNumber(c); 
            if(num !== 9999 && num !== 999 && num > maxNum) maxNum = num; 
        }); 
        newChapterNum.value = maxNum + 1; 
        newChapterTitle.value = ''; 
        showChapterModal.value = true; 
    }; 

    const confirmCreateChapter = async () => { 
        let finalName = `第${newChapterNum.value}章`; 
        if (newChapterTitle.value.trim()) finalName += `_${newChapterTitle.value.trim()}`; 

        try { 
            const res = await fetch(`/api/projects/${projectState.currentProject.value}/chapters/${finalName}`, { method: 'POST' }); 
            if (res.ok) { 
                await projectState.fetchChapters(); 
                projectState.currentChapter.value = finalName + '.txt'; 
                workflowChapterSelect.value = finalName; 
                workflowChapterName.value = finalName; 
                showChapterModal.value = false; 
            } else alert("创建失败，请检查后端状态。"); 
        } catch (e) { alert(`请求异常: ${e.message}`); } 
    }; 

    // ================= 方法：角色解析逻辑 =================
    const loadCharacterSuggestions = async () => {
        if (!selectedReference.value) { alert("请先在上方选择参考书！"); return; }
        isLoadingChars.value = true; showCharSelector.value = true;
        recommendedChars.value = []; freqChars.value = [];

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
                        let name = c, aliases = '';
                        const aliasMatch = c.match(/(.+?)[(（](.+?)[)）]/);
                        if (aliasMatch) { name = aliasMatch[1].trim(); aliases = aliasMatch[2].trim(); }
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
                    const word = m[1], freq = parseInt(m[2]);
                    if (word.length >= 2 && !recommendedChars.value.find(rc => rc.name === word)) {
                        freqChars.value.push({ name: word, freq, selected: false });
                        count++;
                    }
                    if (count >= 40) break;
                }
            }
        } catch (e) { console.error("加载角色失败", e); } 
        finally { isLoadingChars.value = false; }
    };

    const syncCharSelection = () => {
        const chars = [];
        recommendedChars.value.filter(c => c.selected).forEach(c => chars.push(c.aliases ? `${c.name}(${c.aliases})` : c.name));
        freqChars.value.filter(c => c.selected).forEach(c => chars.push(c.name));
        if (customCharInput.value.trim()) {
            chars.push(...customCharInput.value.split(/[,，]/).map(c => c.trim()).filter(Boolean));
        }
        workflowCharName.value = chars.join(', ');
    };
    watch([recommendedChars, freqChars, customCharInput], syncCharSelection, { deep: true });

    // ================= 方法：流水线与脚本执行 =================
    const waitForTask = (taskId) =>  { 
        return new Promise((resolve, reject) =>  { 
            const check = async () => { 
                if (cancelAutoFlag.value) { reject(new Error('用户手动终止了流水线')); return; } 
                try { 
                    const res = await fetch(`/api/tasks/${taskId}` ); 
                    if (res.ok) { 
                        const task = await res.json(); 
                        if (task.status === 'success') resolve(task); 
                        else if (task.status === 'failed' || task.status === 'error') reject(new Error(task.error || task.stderr || '任务执行失败')); 
                        else setTimeout(check, 2000); 
                    } else if (res.status === 404) reject(new Error('系统拦截：任务记录已被物理清理或进程已丢失。')); 
                    else setTimeout(check, 2000); 
                } catch (e) { setTimeout(check, 2000); } 
            }; 
            check(); 
        }); 
    }; 

    const executePipelineStep = async (step, customChar = null) => {
        if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");
        autoRunProgress.value = `${step.script} - ${step.name}`;
        
        let url = `/api/scripts/${step.script}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(step.script)) url += `&model=${workflowStyleModel.value}`;
        if (step.script === 'f3c' && customChar) url += `&character=${encodeURIComponent(customChar)}`;
        
        const res = await fetch(url, { method: 'POST' });
        if (!res.ok) throw new Error(`${step.script} 请求失败`);
        
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        if (data.task_id) await waitForTask(data.task_id);
        await pollTasks();
    };

    const stopAutoPipeline = () => {
        if (isAutoRunning.value || isAutoPaused.value) {
            cancelAutoFlag.value = true;
            autoRunProgress.value = "正在强制终止流水线，等待当前步骤结束...";
        }
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
                alert("前置设定 (f0-f3b) 已提取完成！请在下方点击【获取推荐名单】按钮。");
            } else {
                alert("模仿模式：基础文风提取流水线执行完成！");
                isAutoRunning.value = false; autoRunProgress.value = '';
            }
        } catch (e) {
            if (e.message.includes('手动终止')) alert("已成功终止流水线任务队列。");
            else alert(`流水线执行中断或遇到错误: ${e.message}`);
            isAutoRunning.value = false; isAutoPaused.value = false; autoRunProgress.value = '';
        }
    };

    const continueAutoPipeline = async () => {
        isAutoPaused.value = false;
        if (cancelAutoFlag.value) return; 

        const chars = workflowCharName.value.split(/[,，]/).map(c => c.trim()).filter(Boolean);
        try {
            for (const char of chars) await executePipelineStep({ script: 'f3c', name: `角色卡提取 (${char})` }, char);
            await executePipelineStep({ script: 'f4b', name: '剧情动态压缩建库' });
            alert("同人模式：文风提取与仿写数据流构建全部执行完成！");
        } catch(e) {
            if (e.message.includes('手动终止')) alert("已成功终止流水线任务队列。");
            else alert(`后半段流水线中断: ${e.message}`);
        } finally {
            isAutoRunning.value = false; autoRunProgress.value = '';
        }
    };

    const runStyleScript = async () => {
        if (!selectedReference.value) { alert("请先选择参考原著文件。"); return; }
        let url = `/api/scripts/${workflowStyleScript.value}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(workflowStyleScript.value)) url += `&model=${workflowStyleModel.value}`;
        if (workflowStyleScript.value === 'f3c') {
            if (!workflowCharName.value.trim()) { alert("需指明目标角色名参数。"); return; }
            url += `&character=${encodeURIComponent(workflowCharName.value.trim())}`;
        }
        await fetch(url, { method: 'POST' });
        await pollTasks();
    };

    const runProjectScript = async () => {
        if (!projectState.currentProject.value) { alert("请先选择一个工程项目。"); return; }
        
        if (workflowProjectScript.value === 'f5a') {
            if (!workflowChapterName.value || !workflowChapterBrief.value) { alert("请完善章节名及剧情简述信息。"); return; }
            const res = await fetch('/api/scripts/f5a_outline', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    project_name: projectState.currentProject.value, 
                    chapter_name: workflowChapterName.value, 
                    chapter_brief: workflowChapterBrief.value,
                    model: workflowProjectModel.value
                })
            });
            const data = await res.json();
            if (data.error) { alert("执行错误: " + data.error); return; }
            await pollTasks(); return;
        }

        if (workflowProjectScript.value === 'f4a') {
            let formData = {};
            if (workflowF4aMode.value === 'worldview') {
                if (!f4aWorldview.value.worldview || !f4aWorldview.value.power_system) { alert("世界观和力量体系为必填项"); return; }
                formData = { ...f4aWorldview.value };
            } else {
                if (!f4aChar.value.name || !f4aChar.value.char_type) { alert("角色名和类型为必填项"); return; }
                formData = { ...f4aChar.value };
            }
            const res = await fetch('/api/scripts/f4a_completion', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_file: projectState.currentProject.value.replace('_style_imitation', ''),
                    mode: workflowF4aMode.value, form_data: formData,
                    model: workflowProjectModel.value, project_name: projectState.currentProject.value
                })
            });
            const data = await res.json();
            if (data.error) { alert("执行错误: " + data.error); return; }
            await pollTasks(); return;
        }

        if (workflowProjectScript.value === 'f5b') {
            if (!workflowChapterName.value) { alert("请指定章节名。"); return; }
            const res = await fetch('/api/scripts/f5b_generate', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    project_name: projectState.currentProject.value, 
                    chapter_name: workflowChapterName.value,
                    model: workflowProjectModel.value
                })
            });
            const data = await res.json();
            if (data.error) { alert("执行错误: " + data.error); return; }
            if (data.task_id) {
                alert("小说生成任务已提交后台执行，完成后将自动同步到编辑器！");
                await waitForTask(data.task_id); 
                await projectState.fetchChapters(); 
                projectState.currentChapter.value = workflowChapterName.value.replace('.txt', '') + '.txt';
                await projectState.fetchContent(); 
                alert("章节正文生成完成！已同步显示在左侧编辑器中。");
            }
            await pollTasks(); return;
        }

        let url = `/api/scripts/${workflowProjectScript.value}?project_name=${encodeURIComponent(projectState.currentProject.value)}&model=${workflowProjectModel.value}`;
        if (['f5a', 'f5b', 'f7'].includes(workflowProjectScript.value)) {
             if (!workflowChapterName.value.trim()) { alert("需指明目标章节名。"); return; }
             url += `&chapter_name=${encodeURIComponent(workflowChapterName.value.trim())}`;
        }
        await fetch(url, { method: 'POST' });
        await pollTasks();
    };

    onMounted(() => { loadReferences(); loadStyles(); });

    return {
        taskList, showAllTasks, visibleTasks,
        references, selectedReference, availableStyles, fileInput, uploadFileName,
        projectActionMode, newProjectName, existingProjectSelect, newProjectBranch, newProjectReferenceStyle,
        workflowProjectScript, workflowProjectModel, workflowStyleScript, workflowStyleModel,
        workflowCharName, workflowChapterName, workflowChapterSelect, workflowChapterBrief,
        workflowF4aMode, f4aWorldview, f4aChar,
        showChapterModal, newChapterNum, newChapterTitle,
        recommendedChars, freqChars, customCharInput, showCharSelector, isLoadingChars,
        styleExtractMode, forceOverwrite, autoPipelineType, autoStyleCharNames, isAutoRunning, autoRunProgress, isAutoPaused, cancelAutoFlag,
        
        handleFileUpload, submitUpload, loadReferences, createProject, openCreateModal, confirmCreateChapter,
        loadCharacterSuggestions, stopAutoPipeline, runStyleScriptAuto, continueAutoPipeline, runProjectScript, runStyleScript
    };
}