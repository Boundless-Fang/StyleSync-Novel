// composables/useProject.js 
const { ref, onMounted } = Vue; 

export function useProject() { 
    const activeTab = ref('editor'); 
    const projects = ref([]); 
    const currentProject = ref(''); 
    const chapters = ref([]); 
    const currentChapter = ref(''); 
    const editorContent = ref(''); 
    const saveStatus = ref('已保存'); 
    let saveTimeout = null; 
    
    const projectCharacters = ref([]); // 原版补回 

    const kbProject = ref(''); 
    const kbType = ref('settings'); 
    const kbItems = ref([]); 
    const kbSelectedFile = ref(''); 
    const kbContent = ref(''); 

    const getChapterNumber = (name) => { 
        let arabicMatch = name.match(/\d+/); 
        if (arabicMatch) return parseInt(arabicMatch[0]); 
        let cnMatch = name.match(/第([零一二两三四五六七八九十百千万]+)[章回节卷]/); 
        if (cnMatch) { 
            const cnNum = cnMatch[1]; 
            const cnMap = { '零':0, '一':1, '二':2, '两':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9 }; 
            const cnUnits = { '十':10, '百':100, '千':1000, '万':10000 }; 
            let result = 0; let tmp = 0; 
            for (let i = 0; i < cnNum.length; i++) { 
                let char = cnNum[i]; 
                if (cnUnits[char]) { 
                    let unit = cnUnits[char]; 
                    if (tmp === 0 && unit === 10) tmp = 1; 
                    result += tmp * unit; tmp = 0; 
                } else { tmp = cnMap[char] || 0; } 
            } 
            result += tmp; return result; 
        } 
        return 999999; 
    }; 

    const loadProjects = async () => { 
        const res = await fetch('/api/projects'); 
        projects.value = await res.json(); 
        if(projects.value.length && !currentProject.value) { 
            currentProject.value = projects.value[0]; 
            fetchChapters(); 
            fetchProjectCharacters(); // 原版补回 
        } 
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
        } else { 
            currentChapter.value = ''; editorContent.value = ''; 
        } 
    }; 

    // 原版补回 
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
        } else if (kbType.value === 'characters') { 
            try { 
                const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/characters`); 
                const list = await res.json(); kbItems.value = list.map(c => ({ label: c, value: c + '.md' })); 
            } catch(e) {} 
        } else if (kbType.value === 'outlines') { 
            try { 
                const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/outlines`); 
                const list = await res.json(); kbItems.value = list.map(c => ({ label: c, value: c })); 
            } catch(e) {} 
        } else if (kbType.value === 'prompts') { 
            try { 
                const res = await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/prompts`); 
                const list = await res.json(); kbItems.value = list.map(c => ({ label: c, value: c })); 
            } catch(e) {} 
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
                const data = await res.json(); kbContent.value = data.content; 
            } else kbContent.value = "无法加载数据或文件尚不存在。"; 
        } catch (e) { kbContent.value = "文件读取拦截，请检查环境服务接口配置。"; } 
    }; 

    const saveKbContent = async () => { 
        if (!kbProject.value || !kbSelectedFile.value) return; 
        let filePath = kbSelectedFile.value; 
        if (kbType.value === 'characters') filePath = `character_profiles/${kbSelectedFile.value}`; 
        else if (kbType.value === 'outlines') filePath = `chapter_structures/${kbSelectedFile.value}`; 
        else if (kbType.value === 'prompts') filePath = `chapter_specific_prompts/${kbSelectedFile.value}`; 

        try { 
            await fetch(`/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`, { 
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: kbContent.value }) 
            }); 
            alert("数据节点已物理落盘。"); 
        } catch (e) { alert("执行覆写操作失败。"); } 
    }; 

    onMounted(() => { loadProjects(); }); 

    return { 
        activeTab, projects, currentProject, chapters, currentChapter, editorContent, saveStatus, projectCharacters, 
        kbProject, kbType, kbItems, kbSelectedFile, kbContent, 
        loadProjects, fetchChapters, fetchProjectCharacters, fetchContent, debouncedSave, renameChapter, importToNovel, 
        fetchKbFilesList, fetchKbContent, saveKbContent, getChapterNumber 
    }; 
 } 
