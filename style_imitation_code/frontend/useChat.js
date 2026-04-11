const { ref, computed } = Vue;

export function useChat(config) {
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

    const currentChat = computed(() => chats.value.find(c => c.id === currentChatId.value));
    
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
        chats, currentChatId, currentChat, chatInput, isGenerating,
        createNewChat, copyCurrentChat, clearCurrentChatMessages, 
        sendMessage, stopGeneration, renderMarkdown
    };
}