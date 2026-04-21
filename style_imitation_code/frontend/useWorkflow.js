const { ref, computed, watch } = Vue;

export function useWorkflow(projectModule) {
    const references = ref([]);
    const selectedReference = ref("");

    const styleExtractMode = ref("auto");
    const forceOverwrite = ref(false);
    const autoPipelineType = ref("fanfic");
    const autoStyleCharNames = ref("");
    const isAutoRunning = ref(false);
    const autoRunProgress = ref("");
    const isAutoPaused = ref(false);
    const cancelAutoFlag = ref(false);

    const globalAutoValidate = ref(false);
    const globalAutoMemory = ref(false);

    const fileInput = ref(null);
    const uploadFileName = ref("");
    let uploadFileObj = null;

    const taskList = ref([]);
    const showAllTasks = ref(false);
    const selectedTaskIds = ref([]);
    const openTaskActionMenu = ref("");
    const visibleTasks = computed(() =>
        showAllTasks.value ? taskList.value : taskList.value.slice(0, 5)
    );

    const workflowProjectScript = ref("f5b");
    const workflowProjectModel = ref("deepseek-chat");
    const workflowStyleScript = ref("f1a");
    const workflowStyleModel = ref("deepseek-chat");
    const injectF5bPromptToWorkspaceOnRun = ref(false);
    const f5bPromptOnlyMode = ref(false);

    const recommendedChars = ref([]);
    const freqChars = ref([]);
    const customCharInput = ref("");
    const showCharSelector = ref(false);
    const isLoadingChars = ref(false);

    const workflowCharName = ref("");
    const workflowCharSelect = ref("");
    const workflowChapterNumber = ref("");
    const workflowChapterTitle = ref("");
    const workflowChapterSelect = ref("");
    const workflowChapterBrief = ref("");
    const workflowChapterName = computed(() => {
        if (workflowChapterSelect.value) return workflowChapterSelect.value;
        const number = workflowChapterNumber.value.trim();
        const title = workflowChapterTitle.value.trim();
        if (number && title) return `${number}_${title}`;
        return title || number;
    });

    const showF5aAdvanced = ref(false);
    const createF5aStructureStage = () => ({
        content: "",
        ban: "无",
        narrative: "顺叙",
        depiction: [],
        drive: "场景",
        word_ratio: "",
        reveal: "无",
        foreshadowing: "无",
    });

    const workflowF5aPosition = ref({
        event_stage: "事件推进",
        novel_stage: "中期",
        chapter_functions: ["主线推进"],
        boundary: "",
        person: "有限第三人称",
        perspective: "中立视角",
        characters: "",
        target_words: "3000字左右",
        scene_switch: "一次",
        pace: "中",
        ban: "无",
    });

    const workflowF5aStructure = ref({
        opening: createF5aStructureStage(),
        buildup: createF5aStructureStage(),
        climax: createF5aStructureStage(),
        ending: createF5aStructureStage(),
    });

    const f5aFunctionOptions = [
        "主线推进",
        "引出人物",
        "前情回顾",
        "角色互动",
        "打斗对抗",
        "身份揭示",
        "埋下伏笔",
        "回收伏笔",
        "设定展开",
        "情绪过渡",
    ];
    const f5aNarrativeOptions = ["顺叙", "插叙", "倒叙", "补叙", "双线"];
    const f5aDepictionOptions = [
        "对话与互动",
        "叙事与动作",
        "反应与侧写",
        "解释与说明",
        "环境与外貌",
    ];
    const f5aDriveOptions = ["场景", "动作", "对话", "反应", "说明", "心理", "外貌"];
    const f5aRevealOptions = [
        "无",
        "直接揭示",
        "延迟揭示",
        "假设揭示",
        "对话中带出",
        "他人反应带出",
    ];

    const workflowF4aMode = ref("worldview");
    const workflowF4aInput = ref("");
    const f4aWorldview = ref({
        worldview: "",
        power_system: "",
        type: "",
        heroines: "",
        cheat: "",
        characters: "",
        factions: "",
        history: "",
        resources: "",
        others: "",
    });
    const f4aChar = ref({
        name: "",
        char_type: "男主角",
        char_shape: "圆形人物",
        identity: "",
        personality: "",
        appearance: "",
        ability: "",
        experience: "",
        attitude: "",
    });
    const projectCharacters = ref([]);

    const kbProject = ref("");
    const kbType = ref("settings");
    const kbItems = ref([]);
    const kbSelectedFile = ref("");
    const kbContent = ref("");

    const normalizeCommaSeparatedInput = (value) =>
        value
            .split(/[,，、；;]/)
            .map((item) => item.trim())
            .filter(Boolean);

    const handleApiResponse = async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const errMsg = data.detail
                ? typeof data.detail === "string"
                    ? data.detail
                    : JSON.stringify(data.detail)
                : data.error || `HTTP 错误状态: ${res.status}`;
            throw new Error(errMsg);
        }
        if (data.error) throw new Error(data.error);
        return data;
    };

    const pollTasks = async () => {
        try {
            const res = await fetch("/api/tasks");
            if (res.ok) {
                taskList.value = await res.json();
                const currentIds = new Set(taskList.value.map((task) => task.id));
                selectedTaskIds.value = selectedTaskIds.value.filter((taskId) => currentIds.has(taskId));
            }
        } catch (e) {
            console.error("轮询任务失败", e);
        }
    };
    setInterval(pollTasks, 2000);

    const loadReferences = async () => {
        const res = await fetch("/api/references");
        references.value = await res.json();
    };

    const handleFileUpload = (event) => {
        const file = event.target.files[0];
        if (file) {
            uploadFileName.value = file.name;
            uploadFileObj = file;
        }
    };

    const submitUpload = async () => {
        if (!uploadFileObj) return;
        const formData = new FormData();
        formData.append("file", uploadFileObj);
        try {
            const res = await fetch("/api/references/upload", {
                method: "POST",
                body: formData,
            });
            if (res.ok) {
                alert("参考文本上传成功");
                uploadFileName.value = "";
                uploadFileObj = null;
                if (fileInput.value) fileInput.value.value = "";
                await loadReferences();
                selectedReference.value = formData.get("file").name;
            } else {
                const errData = await res.json().catch(() => ({}));
                alert(`文件上传失败: ${errData.detail || errData.error || "后端异常"}`);
            }
        } catch (e) {
            alert("上传时发生网络异常。");
        }
    };

    const loadCharacterSuggestions = async () => {
        if (!selectedReference.value) {
            alert("请先选择参考书。");
            return;
        }

        isLoadingChars.value = true;
        showCharSelector.value = true;
        recommendedChars.value = [];
        freqChars.value = [];

        const styleName = selectedReference.value.replace(/\.txt$/i, "") + "_style_imitation";
        const fakeProjName = encodeURIComponent(`style@@${styleName}`);

        try {
            const wsRes = await fetch(
                `/api/projects/${fakeProjName}/settings/world_settings.md`
            );
            if (wsRes.ok) {
                const wsData = await wsRes.json();
                const contentStr = wsData.content || "";
                const charsSectionMatch = contentStr.match(
                    /角色.*?[：:]\s*([\s\S]*?)(?=\n[^\n]+[：:]|\n#|$)/
                );

                if (charsSectionMatch && charsSectionMatch[1]) {
                    const rawItems = charsSectionMatch[1].split(/[\n,，、；;]/);
                    rawItems.forEach((item) => {
                        const cleanStr = item.replace(/^[\s*+\->•]+/, "").trim();
                        if (!cleanStr) return;

                        let name = cleanStr;
                        let aliases = "";
                        const aliasMatch = cleanStr.match(/(.+?)[(（](.+?)[)）]/);
                        if (aliasMatch) {
                            name = aliasMatch[1].trim();
                            aliases = aliasMatch[2].trim();
                        }

                        if (name && !recommendedChars.value.find((c) => c.name === name)) {
                            recommendedChars.value.push({
                                name,
                                aliases,
                                selected: true,
                                editing: false,
                            });
                        }
                    });
                }
            }

            const freqRes = await fetch(
                `/api/projects/${fakeProjName}/settings/statistics/高频词.txt`
            );
            if (freqRes.ok) {
                const freqData = await freqRes.json();
                const matches = [...(freqData.content || "").matchAll(/(\S+)\((\d+)\)/g)];
                let count = 0;
                for (const match of matches) {
                    const word = match[1];
                    const freq = parseInt(match[2], 10);
                    if (word.length >= 2 && !recommendedChars.value.find((c) => c.name === word)) {
                        freqChars.value.push({ name: word, freq, selected: false });
                        count += 1;
                    }
                    if (count >= 40) break;
                }
            }
        } catch (e) {
            console.error("加载角色建议失败", e);
        } finally {
            isLoadingChars.value = false;
        }
    };

    const syncCharSelection = () => {
        const chars = [];
        recommendedChars.value
            .filter((c) => c.selected)
            .forEach((c) => chars.push(c.aliases ? `${c.name}(${c.aliases})` : c.name));
        freqChars.value.filter((c) => c.selected).forEach((c) => chars.push(c.name));
        if (customCharInput.value.trim()) {
            chars.push(...normalizeCommaSeparatedInput(customCharInput.value));
        }
        workflowCharName.value = chars.join(", ");
    };

    watch([recommendedChars, freqChars, customCharInput], syncCharSelection, {
        deep: true,
    });

    const stopAutoPipeline = () => {
        if (isAutoRunning.value || isAutoPaused.value) {
            cancelAutoFlag.value = true;
            autoRunProgress.value = "正在强制终止流水线...";
            cancelLatestTask({ silent: true }).catch(() => {});
        }
    };

    const cancelLatestTask = async ({ silent = false } = {}) => {
        try {
            const res = await fetch("/api/tasks/cancel_latest", { method: "POST" });
            const data = await handleApiResponse(res);
            await pollTasks();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`终止最近任务失败: ${e.message}`);
            throw e;
        }
    };

    const cancelAllTasks = async ({ silent = false } = {}) => {
        try {
            const res = await fetch("/api/tasks/cancel_all", { method: "POST" });
            const data = await handleApiResponse(res);
            await pollTasks();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`终止全部任务失败: ${e.message}`);
            throw e;
        }
    };

    const toggleTaskSelection = (taskId) => {
        if (selectedTaskIds.value.includes(taskId)) {
            selectedTaskIds.value = selectedTaskIds.value.filter((id) => id !== taskId);
        } else {
            selectedTaskIds.value = [...selectedTaskIds.value, taskId];
        }
    };

    const isTaskSelected = (taskId) => selectedTaskIds.value.includes(taskId);

    const clearTaskSelection = () => {
        selectedTaskIds.value = [];
    };

    const toggleTaskActionMenu = (menuKey) => {
        openTaskActionMenu.value = openTaskActionMenu.value === menuKey ? "" : menuKey;
    };

    const cancelSelectedTasks = async ({ silent = false } = {}) => {
        if (!selectedTaskIds.value.length) {
            if (!silent) alert("请先勾选任务。");
            return null;
        }
        try {
            const res = await fetch("/api/tasks/cancel_selected", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ task_ids: selectedTaskIds.value }),
            });
            const data = await handleApiResponse(res);
            await pollTasks();
            clearTaskSelection();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`终止勾选任务失败: ${e.message}`);
            throw e;
        } finally {
            openTaskActionMenu.value = "";
        }
    };

    const clearOldestTasks = async ({ silent = false } = {}) => {
        try {
            const res = await fetch("/api/tasks/clear_oldest", { method: "POST" });
            const data = await handleApiResponse(res);
            await pollTasks();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`清除最远任务失败: ${e.message}`);
            throw e;
        } finally {
            openTaskActionMenu.value = "";
        }
    };

    const clearAllTaskRecords = async ({ silent = false } = {}) => {
        try {
            const res = await fetch("/api/tasks/clear_all", { method: "POST" });
            const data = await handleApiResponse(res);
            await pollTasks();
            clearTaskSelection();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`清除全部任务失败: ${e.message}`);
            throw e;
        } finally {
            openTaskActionMenu.value = "";
        }
    };

    const clearSelectedTaskRecords = async ({ silent = false } = {}) => {
        if (!selectedTaskIds.value.length) {
            if (!silent) alert("请先勾选任务。");
            return null;
        }
        try {
            const res = await fetch("/api/tasks/clear_selected", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ task_ids: selectedTaskIds.value }),
            });
            const data = await handleApiResponse(res);
            await pollTasks();
            clearTaskSelection();
            if (!silent && data.message) alert(data.message);
            return data;
        } catch (e) {
            if (!silent) alert(`清除勾选任务失败: ${e.message}`);
            throw e;
        } finally {
            openTaskActionMenu.value = "";
        }
    };

    const waitForTask = (taskId) =>
        new Promise((resolve, reject) => {
            const check = async () => {
                if (cancelAutoFlag.value) {
                    reject(new Error("用户手动终止了流水线"));
                    return;
                }
                try {
                    const res = await fetch(`/api/tasks/${taskId}`);
                    if (res.ok) {
                        const task = await res.json();
                        if (task.status === "success") resolve(task);
                        else if (task.status === "cancelled") reject(new Error(task.error || "任务已取消"));
                        else if (task.status === "failed" || task.status === "error") {
                            reject(new Error(task.error || task.stderr || "任务执行失败"));
                        } else {
                            setTimeout(check, 2000);
                        }
                    } else if (res.status === 404) {
                        reject(new Error("任务记录已被清理或进程已丢失。"));
                    } else {
                        setTimeout(check, 2000);
                    }
                } catch (e) {
                    setTimeout(check, 2000);
                }
            };
            check();
        });

    const buildF5aPayload = () => {
        const cleanStage = (stage) => ({
            content: stage.content.trim(),
            ban: (stage.ban || "无").trim() || "无",
            narrative: stage.narrative,
            depiction: stage.depiction,
            drive: stage.drive,
            word_ratio: stage.word_ratio.trim(),
            reveal: stage.reveal,
            foreshadowing: (stage.foreshadowing || "无").trim() || "无",
        });

        return {
            chapter_brief: workflowChapterBrief.value.trim(),
            chapter_boundary: workflowF5aPosition.value.boundary.trim(),
            event_stage: workflowF5aPosition.value.event_stage,
            novel_stage: workflowF5aPosition.value.novel_stage,
            chapter_functions: workflowF5aPosition.value.chapter_functions,
            person: workflowF5aPosition.value.person,
            perspective: workflowF5aPosition.value.perspective,
            characters: normalizeCommaSeparatedInput(workflowF5aPosition.value.characters),
            target_words: workflowF5aPosition.value.target_words.trim(),
            scene_switch: workflowF5aPosition.value.scene_switch,
            pace: workflowF5aPosition.value.pace,
            ban: (workflowF5aPosition.value.ban || "无").trim() || "无",
            structure: {
                opening: cleanStage(workflowF5aStructure.value.opening),
                buildup: cleanStage(workflowF5aStructure.value.buildup),
                climax: cleanStage(workflowF5aStructure.value.climax),
                ending: cleanStage(workflowF5aStructure.value.ending),
            },
        };
    };

    const executePipelineStep = async (step, customChar = null) => {
        if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");
        autoRunProgress.value = `${step.script} - ${step.name}`;

        let url = `/api/scripts/${step.script}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (["f1b", "f2b", "f3a", "f3b", "f3c"].includes(step.script)) {
            url += `&model=${workflowStyleModel.value}`;
        }
        if (step.script === "f3c" && customChar) {
            url += `&character=${encodeURIComponent(customChar)}`;
        }

        const res = await fetch(url, { method: "POST" });
        const data = await handleApiResponse(res);
        if (data.task_id) await waitForTask(data.task_id);
        await pollTasks();
    };

    const runStyleScriptAuto = async () => {
        if (!selectedReference.value) {
            alert("请先选择参考原著文件。");
            return;
        }

        isAutoRunning.value = true;
        isAutoPaused.value = false;
        cancelAutoFlag.value = false;

        const stepsPhase1 = [
            { script: "f0", name: "全局基础 RAG 库初始化" },
            { script: "f1a", name: "本地统计指标计算" },
            { script: "f1b", name: "文风特征提取" },
            { script: "f2a", name: "高频词提取" },
            { script: "f2b", name: "基础词库整理" },
        ];

        if (autoPipelineType.value === "fanfic") {
            stepsPhase1.push({ script: "f3a", name: "专属词库提取" });
            stepsPhase1.push({ script: "f3b", name: "世界观整理" });
        }

        try {
            for (const step of stepsPhase1) await executePipelineStep(step);
            if (cancelAutoFlag.value) throw new Error("用户手动终止了流水线");

            if (autoPipelineType.value === "fanfic") {
                autoRunProgress.value = "等待人工确认角色名单...";
                isAutoPaused.value = true;
                alert("前置设定提取已完成，请获取角色列表并确认后继续。");
            } else {
                alert("基础文风提取流程已执行完成。");
                isAutoRunning.value = false;
                autoRunProgress.value = "";
            }
        } catch (e) {
            alert(
                e.message.includes("手动终止")
                    ? "已成功终止流水线任务。"
                    : `流水线中断: ${e.message}`
            );
            isAutoRunning.value = false;
            isAutoPaused.value = false;
            autoRunProgress.value = "";
        }
    };

    const continueAutoPipeline = async () => {
        isAutoPaused.value = false;
        if (cancelAutoFlag.value) return;

        const chars = normalizeCommaSeparatedInput(workflowCharName.value);
        try {
            for (const char of chars) {
                await executePipelineStep({ script: "f3c", name: `角色卡提取 (${char})` }, char);
            }
            await executePipelineStep({ script: "f4b", name: "剧情摘要压缩与记忆构建" });
            alert("同人模式的风格提取与仿写数据流已全部执行完成。");
        } catch (e) {
            alert(
                e.message.includes("手动终止")
                    ? "已成功终止任务队列。"
                    : `后半段流水线中断: ${e.message}`
            );
        } finally {
            isAutoRunning.value = false;
            autoRunProgress.value = "";
        }
    };

    const runProjectScript = async () => {
        if (!projectModule.currentProject.value) {
            alert("请先选择一个工程项目。");
            return;
        }

        const curProj = projectModule.currentProject.value;

        const triggerAutoMemory = async () => {
            if (!globalAutoMemory.value) return;
            const url = `/api/scripts/f4c?project_name=${encodeURIComponent(curProj)}&force=true`;
            const res = await fetch(url, { method: "POST" });
            const data = await handleApiResponse(res);
            if (data.task_id) {
                alert("已自动触发 f4c 前文记忆库构建，请等待执行完成。");
                await waitForTask(data.task_id);
                alert("前文记忆库构建完成。");
            }
        };

        const triggerAutoValidation = async (targetNode) => {
            if (!globalAutoValidate.value) return;
            const chapter = workflowChapterName.value.trim();
            if (!chapter) return;

            const url = `/api/scripts/f7?project_name=${encodeURIComponent(curProj)}&model=${workflowProjectModel.value}&chapter_name=${encodeURIComponent(chapter)}`;
            const res = await fetch(url, { method: "POST" });
            const data = await handleApiResponse(res);
            if (data.task_id) {
                alert(`已自动触发 [${targetNode}] 节点的 f7 文本校验，请等待完成。`);
                await waitForTask(data.task_id);
                alert(`【全局校验完成】[${targetNode}] 流程已结束。`);
            }
        };

        if (workflowProjectScript.value === "f4a") {
            const formData =
                workflowF4aMode.value === "worldview" ? f4aWorldview.value : f4aChar.value;
            try {
                const res = await fetch("/api/scripts/f4a_completion", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        project_name: curProj,
                        mode: workflowF4aMode.value,
                        target_file: selectedReference.value || "",
                        model: workflowProjectModel.value,
                        form_data: formData,
                    }),
                });
                const data = await handleApiResponse(res);
                if (data.task_id) alert("设定补全任务已提交，请查看左侧任务面板。");
            } catch (e) {
                alert(`设定补全触发失败: ${e.message}`);
            }
            await pollTasks();
            return;
        }

        if (workflowProjectScript.value === "f5a") {
            if (!workflowChapterBrief.value.trim()) {
                alert("请至少填写本章梗概。");
                return;
            }

            try {
                await triggerAutoMemory();
                const outlineChapterName =
                    workflowChapterName.value.trim() ||
                    `未命名章节_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;

                const res = await fetch("/api/scripts/f5a_outline", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        project_name: curProj,
                        chapter_name: outlineChapterName,
                        chapter_brief: buildF5aPayload(),
                        model: workflowProjectModel.value,
                    }),
                });
                const data = await handleApiResponse(res);
                if (data.task_id) {
                    await waitForTask(data.task_id);
                    await triggerAutoValidation("f5a");
                }
            } catch (e) {
                alert(`大纲生成请求异常: ${e.message}`);
            }
            await pollTasks();
            return;
        }

        if (workflowProjectScript.value === "f5b") {
            const chapterName = workflowChapterName.value.trim();
            if (!chapterName) {
                alert("请指定章节名。");
                return;
            }

            try {
                await triggerAutoMemory();
                if (injectF5bPromptToWorkspaceOnRun.value) {
                    await injectF5bPromptToWorkspace();
                    if (f5bPromptOnlyMode.value) {
                        await pollTasks();
                        return;
                    }
                }
                const res = await fetch("/api/scripts/f5b_generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        project_name: curProj,
                        chapter_name: chapterName,
                        model: workflowProjectModel.value,
                    }),
                });
                const data = await handleApiResponse(res);
                if (data.task_id) {
                    alert(
                        `生成任务已提交，完成后将自动同步${
                            globalAutoValidate.value ? "，并执行文本校验" : ""
                        }。`
                    );
                    await waitForTask(data.task_id);
                    await projectModule.fetchChapters();
                    projectModule.currentChapter.value = `${chapterName.replace(".txt", "")}.txt`;
                    await projectModule.fetchContent();

                    if (globalAutoValidate.value) {
                        await triggerAutoValidation("f5b");
                    } else {
                        alert("章节正文生成完成，已同步显示在编辑器中。");
                    }
                }
            } catch (e) {
                alert(`正文生成请求异常: ${e.message}`);
            }
            await pollTasks();
            return;
        }

        try {
            let url = `/api/scripts/${workflowProjectScript.value}?project_name=${encodeURIComponent(curProj)}&model=${workflowProjectModel.value}`;
            if (workflowProjectScript.value === "f7" && workflowChapterName.value.trim()) {
                url += `&chapter_name=${encodeURIComponent(workflowChapterName.value.trim())}`;
            }
            const res = await fetch(url, { method: "POST" });
            await handleApiResponse(res);
        } catch (e) {
            alert(`辅助脚本执行异常: ${e.message}`);
        }
        await pollTasks();
    };

    const runStyleScript = async () => {
        if (!selectedReference.value) {
            alert("请先选择参考原著文件。");
            return;
        }

        let url = `/api/scripts/${workflowStyleScript.value}?target_file=${encodeURIComponent(selectedReference.value)}&force=${forceOverwrite.value}`;
        if (["f1b", "f2b", "f3a", "f3b", "f3c"].includes(workflowStyleScript.value)) {
            url += `&model=${workflowStyleModel.value}`;
        }
        if (workflowStyleScript.value === "f3c") {
            if (!workflowCharName.value.trim()) {
                alert("需要指定目标角色名。");
                return;
            }
            url += `&character=${encodeURIComponent(workflowCharName.value.trim())}`;
        }

        try {
            const res = await fetch(url, { method: "POST" });
            await handleApiResponse(res);
        } catch (e) {
            alert(`特征提取脚本执行异常: ${e.message}`);
        }
        await pollTasks();
    };

    const fetchKbFilesList = async () => {
        kbSelectedFile.value = "";
        kbContent.value = "";
        kbItems.value = [];
        if (!kbProject.value) return;

        if (kbType.value === "settings") {
            kbItems.value = [
                { label: "文风特征设定 (features.md)", value: "features.md" },
                { label: "世界观设定 (world_settings.md)", value: "world_settings.md" },
                { label: "正面词库 (positive_words.md)", value: "positive_words.md" },
                { label: "负面词库 (negative_words.md)", value: "negative_words.md" },
                { label: "专属词库 (exclusive_vocab.md)", value: "exclusive_vocab.md" },
                { label: "剧情大纲 (plot_outlines.md)", value: "plot_outlines.md" },
            ];
            return;
        }

        const endpoints = { characters: "characters", outlines: "outlines", prompts: "prompts" };
        try {
            const res = await fetch(
                `/api/projects/${encodeURIComponent(kbProject.value)}/${endpoints[kbType.value]}`
            );
            const list = await res.json();
            kbItems.value = list.map((item) => ({
                label: item,
                value: kbType.value === "characters" ? `${item}.md` : item,
            }));
        } catch (e) {
            console.error("加载知识库文件列表失败", e);
        }
    };

    const fetchKbContent = async () => {
        if (!kbProject.value || !kbSelectedFile.value) return;
        let filePath = kbSelectedFile.value;
        if (kbType.value === "characters") filePath = `character_profiles/${kbSelectedFile.value}`;
        else if (kbType.value === "outlines") filePath = `chapter_structures/${kbSelectedFile.value}`;
        else if (kbType.value === "prompts") filePath = `chapter_specific_prompts/${kbSelectedFile.value}`;

        try {
            const res = await fetch(
                `/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`
            );
            if (res.ok) {
                const data = await res.json();
                kbContent.value = data.content;
            } else {
                kbContent.value = "无法加载数据或文件尚不存在。";
            }
        } catch (e) {
            kbContent.value = "文件读取失败。";
        }
    };

    const saveKbContent = async () => {
        if (!kbProject.value || !kbSelectedFile.value) return;
        let filePath = kbSelectedFile.value;
        if (kbType.value === "characters") filePath = `character_profiles/${kbSelectedFile.value}`;
        else if (kbType.value === "outlines") filePath = `chapter_structures/${kbSelectedFile.value}`;
        else if (kbType.value === "prompts") filePath = `chapter_specific_prompts/${kbSelectedFile.value}`;

        try {
            const res = await fetch(
                `/api/projects/${encodeURIComponent(kbProject.value)}/settings/${filePath}`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content: kbContent.value }),
                }
            );
            await handleApiResponse(res);
            alert("数据节点已保存。");
        } catch (e) {
            alert(`保存失败: ${e.message}`);
        }
    };

    const injectF5bPromptToWorkspace = async () => {
        if (!projectModule.currentProject.value) {
            alert("请先选择一个工程项目。");
            return;
        }

        const chapterName = workflowChapterName.value.trim();
        if (!chapterName) {
            alert("请先指定章节名，再导出 f5b 提示词。");
            return;
        }

        try {
            const res = await fetch("/api/scripts/f5b_prompt_export", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_name: projectModule.currentProject.value,
                    chapter_name: chapterName,
                    model: workflowProjectModel.value,
                }),
            });
            const data = await handleApiResponse(res);
            window.dispatchEvent(
                new CustomEvent("style-sync:inject-workspace", {
                    detail: {
                        templateKey: "generate_draft",
                        content: data.prompt || "",
                        label: `f5b提示词注入: ${chapterName}`,
                    },
                })
            );
            alert("f5b 提示词已注入工作台输入框。");
        } catch (e) {
            alert(`提示词注入失败: ${e.message}`);
        }
    };

    return {
        references,
        selectedReference,
        styleExtractMode,
        forceOverwrite,
        autoPipelineType,
        autoStyleCharNames,
        isAutoRunning,
        autoRunProgress,
        isAutoPaused,
        cancelAutoFlag,
        globalAutoValidate,
        globalAutoMemory,
        fileInput,
        uploadFileName,
        taskList,
        showAllTasks,
        selectedTaskIds,
        openTaskActionMenu,
        visibleTasks,
        workflowProjectScript,
        workflowProjectModel,
        workflowStyleScript,
        workflowStyleModel,
        injectF5bPromptToWorkspaceOnRun,
        f5bPromptOnlyMode,
        recommendedChars,
        freqChars,
        customCharInput,
        showCharSelector,
        isLoadingChars,
        workflowCharName,
        workflowCharSelect,
        workflowChapterNumber,
        workflowChapterTitle,
        workflowChapterName,
        workflowChapterSelect,
        workflowChapterBrief,
        showF5aAdvanced,
        workflowF4aMode,
        workflowF4aInput,
        workflowF5aPosition,
        workflowF5aStructure,
        f5aFunctionOptions,
        f5aNarrativeOptions,
        f5aDepictionOptions,
        f5aDriveOptions,
        f5aRevealOptions,
        f4aWorldview,
        f4aChar,
        projectCharacters,
        kbProject,
        kbType,
        kbItems,
        kbSelectedFile,
        kbContent,
        loadReferences,
        handleFileUpload,
        submitUpload,
        loadCharacterSuggestions,
        stopAutoPipeline,
        cancelLatestTask,
        cancelAllTasks,
        cancelSelectedTasks,
        clearOldestTasks,
        clearAllTaskRecords,
        clearSelectedTaskRecords,
        toggleTaskSelection,
        isTaskSelected,
        clearTaskSelection,
        toggleTaskActionMenu,
        executePipelineStep,
        runStyleScriptAuto,
        continueAutoPipeline,
        runProjectScript,
        runStyleScript,
        fetchKbFilesList,
        fetchKbContent,
        saveKbContent,
        injectF5bPromptToWorkspace,
    };
}
