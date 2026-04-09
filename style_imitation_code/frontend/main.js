// main.js 
const { createApp } = Vue; 

import { useChat } from './composables/useChat.js'; 
import { useProject } from './composables/useProject.js'; 
import { useWorkflow } from './composables/useWorkflow.js'; 
import { useUtils } from './utils/common.js'; 

createApp({ 
    setup() { 
        const utilsState = useUtils(); 
        const projectState = useProject(); 
        // 完美修复：只把单纯的 config 传进去，正则由内部动态计算 
        const chatState = useChat(utilsState.config); 
        const workflowState = useWorkflow(projectState); 

        return { 
            ...utilsState, 
            ...projectState, 
            ...chatState, 
            ...workflowState 
        }; 
    } 
}).mount('#app'); 
