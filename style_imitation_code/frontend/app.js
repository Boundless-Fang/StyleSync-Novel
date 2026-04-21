const { createApp, ref, onMounted } = Vue;

import { useChat } from './useChat.js';
import { useProject } from './useProject.js';
import { useWorkflow } from './useWorkflow.js';

const DEFAULT_UI_CONFIG = {
    showWorkspace: true,
    layoutRatio: 50,
    fontSize: 15,
    composerHeight: 120,
    globalForbidden: '政治,暴力,色情',
    retryLimit: 1,
    forbiddenTolerance: 3,
};

createApp({
    setup() {
        // 全局基础配置
        const config = ref({
            showWorkspace: DEFAULT_UI_CONFIG.showWorkspace,
            layoutRatio: DEFAULT_UI_CONFIG.layoutRatio,
            fontSize: DEFAULT_UI_CONFIG.fontSize,
            apiKey: localStorage.getItem('deepseekApiKey') || '',
            globalForbidden: DEFAULT_UI_CONFIG.globalForbidden,
            retryLimit: DEFAULT_UI_CONFIG.retryLimit,
            forbiddenTolerance: DEFAULT_UI_CONFIG.forbiddenTolerance,
            composerHeight: parseInt(localStorage.getItem('workspaceComposerHeight') || String(DEFAULT_UI_CONFIG.composerHeight), 10)
        });

        // 监听 API Key 变动并持久化
        Vue.watch(() => config.value.apiKey, val => localStorage.setItem('deepseekApiKey', val));
        Vue.watch(() => config.value.composerHeight, val => localStorage.setItem('workspaceComposerHeight', String(val)));

        const resetDisplayDefaults = () => {
            config.value.showWorkspace = DEFAULT_UI_CONFIG.showWorkspace;
            config.value.layoutRatio = DEFAULT_UI_CONFIG.layoutRatio;
            config.value.fontSize = DEFAULT_UI_CONFIG.fontSize;
            config.value.composerHeight = DEFAULT_UI_CONFIG.composerHeight;
        };

        // 挂载三大领域模块
        const projectModule = useProject();
        const workflowModule = useWorkflow(projectModule); 
        const chatModule = useChat(config, projectModule, workflowModule);

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
            resetDisplayDefaults,
            ...chatModule,
            ...projectModule,
            ...workflowModule,
            addChapterFromWorkflow
        };
    }
}).mount('#app');
