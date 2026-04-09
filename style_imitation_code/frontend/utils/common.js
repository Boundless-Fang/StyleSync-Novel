// utils/common.js 
const { ref, watch } = Vue; 

export function useUtils() { 
    // ================= 1. 全局配置状态 ================= 
    const config = ref({ 
        showWorkspace: true, 
        layoutRatio: 45, 
        fontSize: 14, 
        apiKey: localStorage.getItem('deepseekApiKey') || '', 
        globalForbidden: '政治,暴力,色情', 
        retryLimit: 1, 
        forbiddenTolerance: 3 
    }); 

    watch(() => config.value.apiKey, val => localStorage.setItem('deepseekApiKey', val)); 

    // ================= 2. 纯函数工具箱 ================= 
    const formatters = { 
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

    return { 
        config, 
        formatters 
    }; 
} 
