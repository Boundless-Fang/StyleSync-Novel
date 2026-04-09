// utils/common.js
const { ref, computed, watch } = Vue;

export function useUtils() {
    // ================= 1. 全局配置状态 (Config) =================
    const config = ref({
        showWorkspace: true,
        layoutRatio: 45,
        fontSize: 14,
        apiKey: localStorage.getItem('deepseekApiKey') || '',
        globalForbidden: '政治,暴力,色情',
        retryLimit: 1,
        forbiddenTolerance: 3 
    });

    // 监听 API Key 变化并持久化至本地
    watch(() => config.value.apiKey, val => localStorage.setItem('deepseekApiKey', val));

    // ================= 2. 敏感词正则拦截器 =================
    // 供全局计算，动态生成正则对象，避免每次渲染重复 new RegExp
    const forbiddenRegex = computed(() => {
        const globalWords = config.value.globalForbidden.split(/[,，、\n\s]+/).map(w => w.trim()).filter(Boolean);
        if (globalWords.length === 0) return null;
        return new RegExp(`(${globalWords.join('|')})`, 'gi');
    });

    // ================= 3. 纯函数工具箱 (Formatters) =================
    const formatters = {
        // 中文数字转阿拉伯数字 (解决第十章排在第二章前面的排序 Bug)
        getChapterNumber: (name) => { 
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
        }
    };

    // ================= 4. Markdown 安全渲染引擎 =================
    // 结合 Marked 解析、DOMPurify 防 XSS 注入与全局/局部敏感词高亮
    const renderMarkdown = (text, localForbiddenRegex = null) => {
        if (!text) return '';
        
        // 1. 将 Markdown 解析为 HTML
        let parsedHtml = marked.parse(text);
        
        // 2. 使用 DOMPurify 清洗危险标签
        parsedHtml = DOMPurify.sanitize(parsedHtml);
        
        // 3. 替换全局敏感词高亮
        if (forbiddenRegex.value) {
            parsedHtml = parsedHtml.replace(forbiddenRegex.value, '<span class="forbidden-highlight">$1</span>');
        }

        // 4. 替换局部对话敏感词高亮 (如果传入)
        if (localForbiddenRegex) {
            parsedHtml = parsedHtml.replace(localForbiddenRegex, '<span class="forbidden-highlight">$1</span>');
        }
        
        return parsedHtml;
    };

    return {
        config,
        forbiddenRegex,
        formatters,
        renderMarkdown
    };
}