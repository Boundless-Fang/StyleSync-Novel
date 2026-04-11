const { createApp, ref, onMounted } = Vue;

import { useChat } from './useChat.js';
import { useProject } from './useProject.js';
import { useWorkflow } from './useWorkflow.js';

createApp({
    setup() {
        // 全局基础配置
        const config = ref({
            showWorkspace: true, layoutRatio: 45, fontSize: 14,
            apiKey: localStorage.getItem('deepseekApiKey') || '',
            globalForbidden: '政治,暴力,色情',
            retryLimit: 1, forbiddenTolerance: 3 
        });

        // 监听 API Key 变动并持久化
        Vue.watch(() => config.value.apiKey, val => localStorage.setItem('deepseekApiKey', val));

        // 挂载三大领域模块
        const chatModule = useChat(config);
        const projectModule = useProject();
        const workflowModule = useWorkflow(projectModule); 

        // 工作流中的快速新建章节需要连接到项目模块
        const addChapterFromWorkflow = async () => {
            const finalName = await projectModule.confirmCreateChapter();
            if(finalName) {
                workflowModule.workflowChapterSelect.value = finalName;
                workflowModule.workflowChapterName.value = finalName;
            }
        };

        onMounted(() => {
            projectModule.loadProjects();
            projectModule.loadStyles();
            workflowModule.loadReferences();
        });

        // 将所有模块的数据与方法扁平化返回，供给 index.html 原封不动地使用
        return {
            config,
            ...chatModule,
            ...projectModule,
            ...workflowModule,
            addChapterFromWorkflow
        };
    }
}).mount('#app');