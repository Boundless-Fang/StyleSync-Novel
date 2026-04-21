const { ref, computed } = Vue;

export function useChat(config, projectModule, workflowModule) {
    const COMPOSER_FOCUS_EXTRA = 84;
    const DEFAULT_CHAT_PARAMS = {
        model: 'deepseek-chat',
        systemPrompt: '',
        localForbidden: '',
        temperature: 1.5,
        top_p: 0.9,
        max_tokens: null,
    };
    const getNewChatTemplate = (id, title) => ({
        id,
        title,
        model: DEFAULT_CHAT_PARAMS.model,
        systemPrompt: DEFAULT_CHAT_PARAMS.systemPrompt,
        localForbidden: DEFAULT_CHAT_PARAMS.localForbidden,
        temperature: DEFAULT_CHAT_PARAMS.temperature,
        top_p: DEFAULT_CHAT_PARAMS.top_p,
        max_tokens: DEFAULT_CHAT_PARAMS.max_tokens,
        stats: { local_hit_count: 0, total_tokens: 0 }, messages: []
    });

    const chats = ref([ getNewChatTemplate('chat_1', '默认对话') ]);
    const currentChatId = ref('chat_1');
    const chatInput = ref('');
    const isGenerating = ref(false);
    const isComposerFocused = ref(false);
    let abortController = null;

    const currentChat = computed(() => chats.value.find(c => c.id === currentChatId.value));
    const composerHeight = computed(() => {
        const baseHeight = Number(config.value.composerHeight) || 56;
        return isComposerFocused.value ? baseHeight + COMPOSER_FOCUS_EXTRA : baseHeight;
    });
    const quickPromptButtons = [
        { key: 'modify_character', label: '修改角色卡', icon: 'fa-solid fa-user-pen' },
        { key: 'modify_world', label: '修改世界观', icon: 'fa-solid fa-earth-asia' },
        { key: 'polish_outline', label: '润色章节大纲', icon: 'fa-solid fa-list-check' },
        { key: 'generate_draft', label: '生成正文', icon: 'fa-solid fa-wand-magic-sparkles' },
        { key: 'revise_chapter', label: '修改小说正文', icon: 'fa-solid fa-file-pen' }
    ];
    const lastInjectedLabel = ref('');
    const lastInjectedTemplate = ref('');
    
    const forbiddenRegex = computed(() => {
        const globalWords = config.value.globalForbidden.split(/[,，、\n\s]+/).map(w => w.trim()).filter(Boolean);
        const localWords = (currentChat.value?.localForbidden || '').split(/[,，、\n\s]+/).map(w => w.trim()).filter(Boolean);
        const allWords = [...new Set([...globalWords, ...localWords])];
        if (allWords.length === 0) return null;
        return new RegExp(`(${allWords.join('|')})`, 'gi');
    });

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

    const resetCurrentChatDefaults = () => {
        if (!currentChat.value) return;
        currentChat.value.model = DEFAULT_CHAT_PARAMS.model;
        currentChat.value.systemPrompt = DEFAULT_CHAT_PARAMS.systemPrompt;
        currentChat.value.localForbidden = DEFAULT_CHAT_PARAMS.localForbidden;
        currentChat.value.temperature = DEFAULT_CHAT_PARAMS.temperature;
        currentChat.value.top_p = DEFAULT_CHAT_PARAMS.top_p;
    };

    const scrollToBottom = () => {
        setTimeout(() => {
            const el = document.getElementById('chatContainer');
            if(el) el.scrollTop = el.scrollHeight;
        }, 50);
    };

    const focusComposer = () => {
        setTimeout(() => {
            const input = document.getElementById('workspaceComposer');
            if (input) input.focus();
        }, 50);
    };

    const stopGeneration = () => {
        if (abortController) {
            abortController.abort();
            isGenerating.value = false;
        }
    };

    const handleComposerFocus = () => {
        isComposerFocused.value = true;
    };

    const handleComposerBlur = () => {
        isComposerFocused.value = false;
    };

    const PROMPT_TEMPLATES = {
        modify_character: (content = '') =>
            `请基于以下角色卡进行修改与补全，保持人物核心设定不变，并输出一版更清晰的角色卡。\n\n修改目标：\n1. 补足动机、能力、关系与冲突点\n2. 删除重复描述，统一人设口径\n3. 若发现设定漏洞，请单独列出\n\n角色卡原文：\n${content || '[请在此粘贴角色卡内容]'}`,
        modify_world: (content = '') =>
            `请基于以下世界观设定进行修订，保持整体风格一致，并重点检查规则漏洞与叙事可用性。\n\n输出要求：\n1. 保留已有核心设定\n2. 补全缺失规则、势力关系或时代背景\n3. 如果存在冲突，请给出“问题 - 建议修订”\n\n世界观原文：\n${content || '[请在此粘贴世界观内容]'}`,
        polish_outline: (content = '') =>
            `请润色以下章节大纲，使其更适合后续正文生成。\n\n优化方向：\n1. 强化冲突、推进与节奏\n2. 标出本章钩子或收束点\n3. 尽量避免剧情断裂与信息重复\n\n章节大纲：\n${content || '[请在此粘贴章节大纲]'}`,
        generate_draft: (content = '') =>
            `请基于以下提示词、设定或大纲直接生成小说正文。\n\n要求：\n1. 保持文风统一\n2. 注意角色称呼、世界观规则与上下文一致\n3. 直接输出正文，不要解释过程\n\n生成依据：\n${content || '[请在此粘贴 f5b 导出的提示词 / 大纲 / 设定]'}`,
        revise_chapter: (content = '') =>
            `请在尽量保留剧情事实、人物关系与文风的前提下，修改以下小说正文。\n\n修改目标：\n1. 优化语言流畅度与节奏\n2. 修复不自然表达、重复句式或逻辑跳跃\n3. 不要擅自改动关键剧情结论\n\n待修改正文：\n${content || '[请在此粘贴章节正文]'}`,
    };

    const buildPromptText = (templateKey, content = '') => {
        const builder = PROMPT_TEMPLATES[templateKey];
        return builder ? builder(content) : content;
    };

    const injectIntoWorkspace = (templateKey, content = '', label = '') => {
        const promptText = buildPromptText(templateKey, content);
        chatInput.value = promptText;
        lastInjectedLabel.value = label || quickPromptButtons.find((item) => item.key === templateKey)?.label || '';
        lastInjectedTemplate.value = quickPromptButtons.find((item) => item.key === templateKey)?.label || '自定义模板';
        if (!currentChat.value) createNewChat();
        focusComposer();
        scrollToBottom();
    };

    const applyQuickPrompt = (templateKey) => {
        injectIntoWorkspace(templateKey, '', quickPromptButtons.find((item) => item.key === templateKey)?.label || '');
    };

    const inferKnowledgeTemplate = () => {
        const kbType = workflowModule?.kbType?.value || '';
        const selectedFile = workflowModule?.kbSelectedFile?.value || '';

        if (kbType === 'characters') return 'modify_character';
        if (kbType === 'outlines') return 'polish_outline';
        if (kbType === 'prompts') return 'generate_draft';
        if (selectedFile.includes('world_settings')) return 'modify_world';
        if (selectedFile.includes('plot_outlines')) return 'polish_outline';
        return 'generate_draft';
    };

    const injectKnowledgeToWorkspace = () => {
        const selectedFile = workflowModule?.kbSelectedFile?.value || '';
        const content = workflowModule?.kbContent?.value || '';
        if (!selectedFile || !content.trim()) {
            alert('请先在知识库中打开一个可用文件。');
            return;
        }

        const templateKey = inferKnowledgeTemplate();

        injectIntoWorkspace(
            templateKey,
            content.trim(),
            `知识库注入: ${selectedFile}`
        );
    };

    const injectEditorContentToWorkspace = () => {
        const editorContent = projectModule?.editorContent?.value || '';
        if (!editorContent.trim()) {
            alert('当前章节正文为空，暂无可注入内容。');
            return;
        }

        const chapterLabel = projectModule.currentChapter?.value || '当前章节';
        injectIntoWorkspace(
            'revise_chapter',
            editorContent.trim(),
            `正文注入: ${chapterLabel}`
        );
    };

    if (typeof window !== 'undefined' && !window.__styleSyncWorkspaceInjectBound) {
        window.addEventListener('style-sync:inject-workspace', (event) => {
            const detail = event?.detail || {};
            injectIntoWorkspace(
                detail.templateKey || 'generate_draft',
                detail.content || '',
                detail.label || '外部注入'
            );
        });
        window.__styleSyncWorkspaceInjectBound = true;
    }

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
            active_version: 0, 
            last_scanned_index: 0, 
            matched_indices: new Set() 
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
                    const scanStart = Math.max(0, aiMessage.last_scanned_index - 200); 
                    const testBlock = currentContent.slice(scanStart); 
                    
                    const matches = [...testBlock.matchAll(forbiddenRegex.value)]; 
                    for (const match of matches) { 
                        const absoluteIndex = scanStart + match.index; 
                        aiMessage.matched_indices.add(absoluteIndex); 
                    } 
                    
                    aiMessage.last_scanned_index = currentContent.length; 
                    currentChat.value.stats.local_hit_count = aiMessage.matched_indices.size; 
                    
                    if (aiMessage.matched_indices.size >= config.value.forbiddenTolerance) { 
                        stopGeneration(); 
                        aiMessage.versions[aiMessage.active_version].content += '\n\n<div class="p-3 bg-red-100 text-red-700 rounded border border-red-300 mt-2 font-bold"><i class="fa-solid fa-triangle-exclamation"></i> 内容触发安全拦截机制：敏感词命中次数 (' + aiMessage.matched_indices.size + ') 已达上限。</div>'; 
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
        let parsedHtml = marked.parse(text);
        parsedHtml = DOMPurify.sanitize(parsedHtml);
        if (forbiddenRegex.value) {
            parsedHtml = parsedHtml.replace(forbiddenRegex.value, '<span class="forbidden-highlight">$1</span>');
        }
        return parsedHtml;
    };

    return {
        chats, currentChatId, currentChat, chatInput, isGenerating, composerHeight,
        quickPromptButtons, lastInjectedLabel, lastInjectedTemplate,
        createNewChat, copyCurrentChat, clearCurrentChatMessages, 
        sendMessage, stopGeneration, renderMarkdown,
        applyQuickPrompt, injectKnowledgeToWorkspace, injectEditorContentToWorkspace,
        handleComposerFocus, handleComposerBlur, resetCurrentChatDefaults
    };
}
