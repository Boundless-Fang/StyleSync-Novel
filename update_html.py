import re

with open('style_imitation_code/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('<div v-if="activeTab === \'workflow\'" class="flex-1 overflow-y-auto p-4 space-y-4">')
end_idx = content.find('        <div v-if="activeTab === \'knowledge\'" class="flex-1 flex flex-col p-4 overflow-hidden space-y-3">')

new_html = '''        <div v-if="activeTab === 'workflow'" class="flex-1 overflow-y-auto p-4 space-y-4">
            <!-- 小说创作工程 (针对 novel_projects) -->
            <div class="bg-white p-5 rounded-lg shadow-sm border border-gray-200">
                <h3 class="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2"><i class="fa-solid fa-rocket text-orange-500"></i> 小说创作工程 (novel_projects)</h3>
                
                <div class="mb-4 p-3 bg-gray-50 border border-gray-200 rounded">
                    <h4 class="text-xs font-bold text-gray-600 mb-2">1. 工程初始化</h4>
                    <input type="text" v-model="newProjectName" placeholder="输入小说书名..." class="w-full text-sm border border-gray-300 rounded p-2 mb-2 focus:ring-1 focus:ring-orange-500 outline-none">
                    
                    <div class="flex gap-4 mb-2">
                        <label class="flex items-center gap-1 text-sm"><input type="radio" v-model="newProjectBranch" value="原创"> 原创</label>
                        <label class="flex items-center gap-1 text-sm"><input type="radio" v-model="newProjectBranch" value="同人"> 同人</label>
                    </div>
                    
                    <select v-if="newProjectBranch === '同人'" v-model="newProjectReferenceStyle" class="w-full text-sm border border-gray-300 rounded p-2 mb-2 bg-white outline-none">
                        <option value="">-- 选择对应的 text_style_imitation 参考数据 --</option>
                        <option v-for="style in availableStyles" :value="style">{{ style }}</option>
                    </select>

                    <button @click="createProject" :disabled="!newProjectName.trim() || (newProjectBranch === '同人' && !newProjectReferenceStyle)" class="w-full py-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white text-sm font-bold rounded shadow-sm transition-colors">
                        创建并初始化工程
                    </button>
                </div>

                <div class="p-3 border border-gray-200 rounded">
                    <h4 class="text-xs font-bold text-gray-600 mb-2">2. 执行创作与辅助功能 (针对当前选中项目)</h4>
                    <p class="text-xs text-gray-400 mb-2">当前选中的项目：<span class="font-bold text-blue-600">{{ currentProject || '未选择' }}</span></p>
                    
                    <label class="text-xs text-gray-500 block mb-1">执行脚本类型</label>
                    <select v-model="workflowProjectScript" class="w-full text-sm border border-gray-300 rounded p-2 mb-3 bg-gray-50 outline-none">
                        <option value="f4a">f4a - 设定补全 (世界观/角色)</option>
                        <option value="f5a">f5a - 章节大纲生成</option>
                        <option value="f5b">f5b - 小说正文生成</option>
                        <option value="f6">f6 - 剧情方向推演</option>
                        <option value="f7">f7 - 文本多维度校验</option>
                    </select>

                    <div class="mb-3">
                        <label class="text-xs text-gray-500 block mb-1">选择推理模型</label>
                        <select v-model="workflowProjectModel" class="w-full text-sm border border-gray-300 rounded p-2 bg-gray-50 outline-none">
                            <option value="deepseek-chat">DeepSeek-V3 (标准模型)</option>
                            <option value="deepseek-reasoner">DeepSeek-R1 (深度推理)</option>
                        </select>
                    </div>

                    <!-- F4A UI -->
                    <div v-if="workflowProjectScript === 'f4a'" class="mb-3">
                        <label class="text-xs text-gray-500 block mb-1">补全模式</label>
                        <select v-model="workflowF4aMode" class="w-full text-sm border border-gray-300 rounded p-2 mb-2 bg-gray-50 outline-none">
                            <option value="worldview">世界观补全 (worldview)</option>
                            <option value="character">角色卡补全 (character)</option>
                        </select>
                        
                        <label class="text-xs text-gray-500 block mb-1">
                            {{ workflowF4aMode === 'worldview' ? '核心世界观设定 (必填)' : '角色基础信息 (JSON格式)' }}
                        </label>
                        <textarea v-if="workflowF4aMode === 'worldview'" v-model="workflowF4aInput" placeholder="请输入核心世界观设定..." class="w-full text-sm border border-gray-300 rounded p-2 h-24 outline-none"></textarea>
                        <textarea v-else v-model="workflowF4aInput" placeholder='{"name": "...", "char_type": "...", ...}' class="w-full text-sm border border-gray-300 rounded p-2 h-24 outline-none font-mono"></textarea>
                        <p class="text-xs text-gray-400 mt-1">注: f4a 需要较复杂的结构化参数，建议参考文档或使用 GUI 客户端。</p>
                    </div>

                    <!-- F5A/F5B/F7 UI -->
                    <div v-if="['f5a', 'f5b', 'f7'].includes(workflowProjectScript)" class="mb-3">
                        <label class="text-xs text-gray-500 block mb-1">目标章节名</label>
                        <div class="flex gap-2">
                            <select v-model="workflowChapterSelect" @change="workflowChapterName = workflowChapterSelect" class="w-1/3 text-sm border border-gray-300 rounded p-2 bg-gray-50 outline-none">
                                <option value="">-- 选择现有章节 --</option>
                                <option v-for="chap in chapters" :value="chap.replace('.txt', '')">{{ chap.replace('.txt', '') }}</option>
                            </select>
                            <input type="text" v-model="workflowChapterName" placeholder="例如：第一章" class="flex-1 text-sm border border-gray-300 rounded p-2 focus:ring-1 focus:ring-blue-500 outline-none">
                        </div>
                    </div>

                    <!-- F5A specific -->
                    <div v-if="workflowProjectScript === 'f5a'" class="mb-3">
                        <label class="text-xs text-gray-500 block mb-1">章节简述 (剧情概要)</label>
                        <textarea v-model="workflowChapterBrief" placeholder="输入本章发生的核心事件..." class="w-full text-sm border border-gray-300 rounded p-2 h-20 outline-none focus:ring-1 focus:ring-blue-500"></textarea>
                    </div>

                    <!-- F5B specific -->
                    <div v-if="workflowProjectScript === 'f5b'" class="mb-3">
                        <label class="text-xs text-gray-500 block mb-1">创作分支</label>
                        <select v-model="workflowF5bBranch" class="w-full text-sm border border-gray-300 rounded p-2 bg-gray-50 outline-none">
                            <option value="同人创作">同人创作 (强约束原著细节)</option>
                            <option value="完全原创">完全原创 (依赖 f4a 设定补全)</option>
                        </select>
                    </div>

                    <button @click="runProjectScript" :disabled="!currentProject" class="w-full py-2 bg-orange-50 hover:bg-orange-100 text-orange-700 disabled:opacity-50 text-sm font-medium rounded transition-colors border border-orange-200">
                        执行创作脚本
                    </button>
                </div>
            </div>

            <!-- 文风与设定提取工作台 (针对 text_style_imitation) -->
            <div class="bg-white p-5 rounded-lg shadow-sm border border-gray-200">
                <h3 class="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2"><i class="fa-solid fa-microchip text-blue-500"></i> 文风与设定提取工作台 (text_style_imitation)</h3>
                
                <label class="text-xs text-gray-500 block mb-1">目标原著文件 (reference_novels)</label>
                <select v-model="selectedReference" class="w-full text-sm border border-gray-300 rounded p-2 mb-3 bg-gray-50 outline-none">
                    <option value="">-- 需选中参考源文件 --</option>
                    <option v-for="ref in references" :value="ref">{{ ref }}</option>
                </select>

                <label class="text-xs text-gray-500 block mb-1">执行提取脚本</label>
                <select v-model="workflowStyleScript" class="w-full text-sm border border-gray-300 rounded p-2 mb-3 bg-gray-50 outline-none">
                    <option value="f1a">f1a - 本地物理指标与TTR统计</option>
                    <option value="f1b">f1b - 大模型深层文风提取</option>
                    <option value="f2a">f2a - 本地高频词提取</option>
                    <option value="f2b">f2b - 大模型词汇清洗分类</option>
                    <option value="f3a">f3a - 专属词库提取</option>
                    <option value="f3b">f3b - 世界观整理</option>
                    <option value="f3c">f3c - 角色卡提取</option>
                    <option value="f4b">f4b - 剧情动态压缩建库</option>
                </select>

                <div v-if="['f1b', 'f2b', 'f3a', 'f3b', 'f3c'].includes(workflowStyleScript)" class="mb-3">
                    <label class="text-xs text-gray-500 block mb-1">选择推理模型</label>
                    <select v-model="workflowStyleModel" class="w-full text-sm border border-gray-300 rounded p-2 bg-gray-50 outline-none">
                        <option value="deepseek-chat">DeepSeek-V3 (标准模型)</option>
                        <option value="deepseek-reasoner">DeepSeek-R1 (深度推理)</option>
                    </select>
                </div>

                <div v-if="workflowStyleScript === 'f3c'" class="mb-3">
                    <label class="text-xs text-gray-500 block mb-1">指定目标角色名 (例如：张小凡)</label>
                    <input type="text" v-model="workflowCharName" placeholder="例如：张小凡" class="w-full text-sm border border-gray-300 rounded p-2 focus:ring-1 focus:ring-blue-500 outline-none">
                </div>

                <button @click="runStyleScript" :disabled="!selectedReference" class="w-full py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 disabled:opacity-50 text-sm font-medium rounded transition-colors border border-blue-200">
                    执行提取脚本
                </button>
            </div>
        </div>
\n'''

new_content = content[:start_idx] + new_html + content[end_idx:]

with open('style_imitation_code/index.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
