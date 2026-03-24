import re

with open('style_imitation_code/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Vue script part
start_js = content.find('const newProjectName = ref(\'\');')
end_js = content.find('const kbProject = ref(\'\');')

new_js = '''            const newProjectName = ref('');
            const newProjectBranch = ref('原创');
            const newProjectReferenceStyle = ref('');
            const availableStyles = ref([]);
            
            const workflowProjectScript = ref('f5b');
            const workflowProjectModel = ref('deepseek-chat');
            const workflowF5bBranch = ref('同人创作');
            
            const workflowStyleScript = ref('f1a');
            const workflowStyleModel = ref('deepseek-chat');

            const workflowCharName = ref('');
            const workflowCharSelect = ref('');
            const workflowChapterName = ref('');
            const workflowChapterSelect = ref('');
            const workflowChapterBrief = ref('');
            const workflowF4aMode = ref('worldview');
            const workflowF4aInput = ref('');
            const projectCharacters = ref([]);

            '''
content = content[:start_js] + new_js + content[end_js:]

# Replace runWorkflowScript
start_run = content.find('const runWorkflowScript = async () => {')
end_run = content.find('const createProject = async () => {')

new_run = '''            const loadStyles = async () => {
                const res = await fetch('/api/styles');
                availableStyles.value = await res.json();
            };
            
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
                    if (!workflowF4aInput.value.trim()) { alert("请输入设定补全参数"); return; }
                    
                    let formData = {};
                    if (workflowF4aMode.value === 'worldview') {
                        formData = { 
                            worldview: workflowF4aInput.value,
                            power_system: "未定义(自动推演)",
                            type: "未定义", heroines: "未定义", cheat: "未定义",
                            characters: "未定义", factions: "未定义", history: "未定义", resources: "未定义", others: ""
                        };
                    } else {
                        try { formData = JSON.parse(workflowF4aInput.value); } 
                        catch(e) { alert("角色模式下必须输入合法的 JSON 格式数据"); return; }
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
                    // 这里未来可以通过 /api/scripts/f5b_generate 传递 workflowF5bBranch 的值
                    fetch('/api/scripts/f5b_generate', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            project_name: currentProject.value, 
                            chapter_name: workflowChapterName.value,
                            model: workflowProjectModel.value,
                            branch: workflowF5bBranch.value
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
                
                let url = `/api/scripts/${workflowStyleScript.value}?target_file=${selectedReference.value}`;
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

            '''
content = content[:start_run] + new_run + content[end_run:]

# Replace createProject
start_create = content.find('const createProject = async () => {')
end_create = content.find('// 知识库文件交互')

new_create = '''const createProject = async () => {
                await fetch('/api/projects', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        name: newProjectName.value,
                        branch: newProjectBranch.value,
                        reference_style: newProjectReferenceStyle.value
                    })
                });
                newProjectName.value = '';
                alert('底层工程目录及配置文件建立完毕。');
                await loadProjects();
                currentProject.value = projects.value[projects.value.length - 1];
                activeTab.value = 'editor';
            };

            '''
content = content[:start_create] + new_create + content[end_create:]

# Replace onMounted
content = content.replace('onMounted(() => { loadProjects(); loadReferences(); });', 'onMounted(() => { loadProjects(); loadReferences(); loadStyles(); });')

# Replace return
content = content.replace('runWorkflowScript, createProject', 'runProjectScript, runStyleScript, createProject')
content = content.replace('workflowModel', 'workflowProjectModel, workflowStyleModel, workflowProjectScript, workflowStyleScript, newProjectBranch, newProjectReferenceStyle, availableStyles, workflowF5bBranch')


with open('style_imitation_code/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
