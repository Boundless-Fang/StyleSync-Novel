const { ref } = Vue;

export function useProject() {
    const activeTab = ref('editor');
    const projects = ref([]);
    const currentProject = ref('');
    const chapters = ref([]);
    const currentChapter = ref('');
    const editorContent = ref('');
    const saveStatus = ref('已保存');
    let saveTimeout = null;

    const projectActionMode = ref('create'); 
    const newProjectName = ref('');
    const existingProjectSelect = ref('');
    const newProjectBranch = ref('原创');
    const newProjectReferenceStyle = ref('');
    const availableStyles = ref([]);

    const showChapterModal = ref(false); 
    const newChapterNum = ref(1); 
    const newChapterTitle = ref(''); 
    
    // 角色名单
    const projectCharacters = ref([]);

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

    const fetchProjectCharacters = async () => { 
        if(!currentProject.value) return; 
        try { 
            const res = await fetch(`/api/projects/${currentProject.value}/characters`); 
            projectCharacters.value = await res.json(); 
        } catch(e) { console.error(e); } 
    };

    const loadProjects = async () => {
        const res = await fetch('/api/projects');
        projects.value = await res.json();
        if(projects.value.length && !currentProject.value) {
            currentProject.value = projects.value[0];
            fetchChapters();
            fetchProjectCharacters(); // 加载项目时同步拉取角色名单
        }
    };

    const loadStyles = async () => {
        const res = await fetch('/api/styles');
        availableStyles.value = await res.json();
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
                showChapterModal.value = false; 
                return finalName; // 返回名称供 workflow 同步
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

    return {
        activeTab, projects, currentProject, chapters, currentChapter, editorContent, saveStatus,
        projectActionMode, newProjectName, existingProjectSelect, newProjectBranch, newProjectReferenceStyle, availableStyles,
        showChapterModal, newChapterNum, newChapterTitle, projectCharacters,
        loadProjects, loadStyles, fetchChapters, fetchContent, debouncedSave, fetchProjectCharacters, 
        openCreateModal, confirmCreateChapter, renameChapter, importToNovel, createProject
    };
}