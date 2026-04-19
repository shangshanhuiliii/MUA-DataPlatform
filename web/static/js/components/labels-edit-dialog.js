class LabelsEditDialog {
    constructor() {
        this.overlay = null;
        this.isInitialized = false;
        this.callback = null;
        this.currentNodeId = null;
        this.currentLabelMeta = {};
        this.hasFinishLabel = false; //是否添加了FINISH标签
    }

    init() {
        if (this.isInitialized) return;

        this.overlay = document.getElementById('labels-edit-dialog-overlay');
        if (!this.overlay) {
            console.error('Labels edit dialog overlay not found');
            return;
        }

        // Close dialog when clicking outside
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });

        // Close dialog on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen()) {
                this.close();
            }
        });

        // Add click event listeners to quick-add label buttons
        this.setupQuickAddLabels();
        // 新增：快速评分按键
        this.setupQuickScoreButtons();

        // 评分输入框：输入后即时校验
        const ratingInput = document.getElementById('finish-rating-input');
        if (ratingInput) {
            ratingInput.addEventListener('input', () => this.syncFinishRating());
            ratingInput.addEventListener('blur', () => this.syncFinishRating());
            ratingInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.syncFinishRating();
            });
        }
        // 标签输入框：控制 NEED_FEEDBACK 反馈输入显示
        const labelsInput = document.getElementById('labels-edit-input');
        if (labelsInput) {
            labelsInput.addEventListener('input', () => {
                this.updateNeedFeedbackArea();
                this.updateFinishControls();
            });
        }
        this.isInitialized = true;
    }

    setupQuickAddLabels() {
        // Find all quick-add label elements
        const labelElements = this.overlay.querySelectorAll('[data-label]');

        labelElements.forEach(element => {
            element.addEventListener('click', (e) => {
                const labelToAdd = e.target.getAttribute('data-label');
                if (labelToAdd) {
                    this.addLabel(labelToAdd);
                    // 新增：点击FINISH后自动聚焦到评分
                    if (labelToAdd === 'FINISH') {
                        const ratingInput = document.getElementById('finish-rating-input');
                        if (ratingInput) ratingInput.focus();
                    }
                }
            });
        });
    }

    addLabel(label) {
        const labelsInput = document.getElementById('labels-edit-input');
        const ratingArea = document.getElementById('finish-rating-area');//新增finish-rating-area
        if (!labelsInput) return;

        const currentValue = labelsInput.value.trim();

        // Parse current labels
        let currentLabels = [];
        if (currentValue) {
            currentLabels = currentValue.split(';').map(l => l.trim()).filter(l => l !== '');
        }

        // Check if label already exists
        if (currentLabels.includes(label)) {
            console.log(`Label "${label}" already exists`);
            return;
        }

        // Add new label
        currentLabels.push(label);

        // Update input value
        labelsInput.value = currentLabels.join(';');
        this.updateNeedFeedbackArea();
        this.updateFinishControls();

        // 添加 FINISH 时提示输入评分
        if (label === 'FINISH' && ratingArea) {
            if (window.showSuccess) {
                showSuccess("请输入评分（0-100）");
            }
        }
    }

// 新增：常用评分快速按键逻辑
    setupQuickScoreButtons() {
        const scoreButtons = this.overlay.querySelectorAll('[data-score]');
        scoreButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const score = e.target.getAttribute('data-score');
                const ratingInput = document.getElementById('finish-rating-input');
                if (ratingInput) {
                    ratingInput.value = score;
                    this.syncFinishRating(); // 点击后直接同步
                }
            });
        });
    }

    parseLabelsString(labelsStr) {
        if (!labelsStr) return [];
        return labelsStr.split(';').map(l => l.trim()).filter(l => l !== '');
    }

    stripScoreLabels(labels) {
        let scoreLabel = null;
        const sanitized = [];

        labels.forEach(label => {
            const num = parseInt(label, 10);
            if (!isNaN(num) && num >= 0 && num <= 100) {
                if (scoreLabel === null) {
                    scoreLabel = num.toString();
                }
            } else {
                sanitized.push(label);
            }
        });

        return { labels: sanitized, scoreLabel };
    }

    sanitizeLabelsInput() {
        const labelsInput = document.getElementById('labels-edit-input');
        if (!labelsInput) {
            return { labels: [], scoreLabel: null };
        }

        const parsed = this.parseLabelsString(labelsInput.value.trim());
        const stripped = this.stripScoreLabels(parsed);
        if (parsed.length !== stripped.labels.length) {
            labelsInput.value = stripped.labels.join(';');
        }
        return stripped;
    }

    // 输入评分时校验
    syncFinishRating() {
        const ratingInput = document.getElementById('finish-rating-input');
        if (!ratingInput || !this.hasFinishLabel) return;

        // 获取并校验评分
        const ratingValue = ratingInput.value.trim();
        if (ratingValue === '') return;
        const rating = parseInt(ratingValue, 10);
        
        // 非法评分不处理
        if (isNaN(rating) || rating < 0 || rating > 100) {
            if (window.showError) {
                showError("有效数字：0-100");
            }
            return;
        }

        ratingInput.value = rating.toString();
    }

    updateNeedFeedbackArea() {
        const needFeedbackArea = document.getElementById('need-feedback-area');
        const needFeedbackQuestionInput = document.getElementById('need-feedback-assistant-question-input');
        const needFeedbackUserFeedbackInput = document.getElementById('need-feedback-user-feedback-input');
        if (!needFeedbackArea) return;

        const { labels } = this.sanitizeLabelsInput();
        const hasNeedFeedback = labels.includes('NEED_FEEDBACK');

        needFeedbackArea.style.display = hasNeedFeedback ? 'block' : 'none';
        if (!hasNeedFeedback) {
            if (needFeedbackQuestionInput) needFeedbackQuestionInput.value = '';
            if (needFeedbackUserFeedbackInput) needFeedbackUserFeedbackInput.value = '';
        }
    }

    updateFinishControls() {
        const ratingArea = document.getElementById('finish-rating-area');
        const ratingInput = document.getElementById('finish-rating-input');
        const finishResponseInput = document.getElementById('finish-assistant-final-input');
        const { labels, scoreLabel } = this.sanitizeLabelsInput();
        const hasFinish = labels.includes('FINISH');

        this.hasFinishLabel = hasFinish;

        if (ratingArea) {
            ratingArea.style.display = hasFinish ? 'block' : 'none';
        }

        if (hasFinish && scoreLabel !== null && ratingInput && (!ratingInput.value || ratingInput.value.trim() === '')) {
            ratingInput.value = scoreLabel;
        }

        if (!hasFinish) {
            if (ratingInput) ratingInput.value = '';
            if (finishResponseInput) finishResponseInput.value = '';
        }
    }

    isOpen() {
        return this.overlay && this.overlay.style.display !== 'none';
    }

    /**
     * Show the labels edit dialog
     * @param {string} nodeId - The node ID to edit labels for
     * @param {string} currentLabels - Current labels as semicolon-separated string
     * @param {Function} callback - Callback function to call with new labels array
     */
    show(nodeId, currentLabels, currentLabelMeta, callback) {
        this.init();
        if (!this.overlay) return;

        this.currentNodeId = nodeId;
        this.currentLabelMeta = currentLabelMeta || {};
        this.callback = callback;

        // Set the labels input value（移除旧的数字评分标签）
        const labelsInput = document.getElementById('labels-edit-input');
        const ratingInput = document.getElementById('finish-rating-input');
        const finishResponseInput = document.getElementById('finish-assistant-final-input');
        let fallbackScoreLabel = '';
        if (labelsInput) {
            const parsedCurrent = this.parseLabelsString(currentLabels || '');
            const stripped = this.stripScoreLabels(parsedCurrent);
            fallbackScoreLabel = stripped.scoreLabel || '';
            labelsInput.value = stripped.labels.join(';');
        }

        // 初始化 NEED_FEEDBACK 文本
        const needFeedbackQuestionInput = document.getElementById('need-feedback-assistant-question-input');
        const needFeedbackUserFeedbackInput = document.getElementById('need-feedback-user-feedback-input');
        const meta = this.currentLabelMeta || {};
        const needFeedbackMeta = meta.NEED_FEEDBACK || {};
        const finishMeta = meta.FINISH || {};
        const fallbackPrompt = needFeedbackMeta.assistant_question || needFeedbackMeta.assistant_prompt || needFeedbackMeta.question || needFeedbackMeta.feedback || '';
        const fallbackUserFeedback = needFeedbackMeta.user_feedback || needFeedbackMeta.response || '';
        if (needFeedbackQuestionInput) {
            needFeedbackQuestionInput.value = fallbackPrompt || '';
        }
        if (needFeedbackUserFeedbackInput) {
            needFeedbackUserFeedbackInput.value = fallbackUserFeedback || '';
        }

        // 初始化 FINISH 元数据（评分 + 最终回复）
        if (ratingInput) {
            let finishScore = '';
            if (finishMeta.score !== undefined && finishMeta.score !== null && finishMeta.score !== '') {
                finishScore = finishMeta.score.toString();
            } else if (fallbackScoreLabel) {
                finishScore = fallbackScoreLabel;
            }
            ratingInput.value = finishScore;
        }
        if (finishResponseInput) {
            finishResponseInput.value = finishMeta.assistant_final_message || finishMeta.final_response || finishMeta.response || '';
        }

        this.updateNeedFeedbackArea();
        this.updateFinishControls();

        // Show dialog
        this.overlay.style.display = 'flex';

        // Focus on input for better UX
        setTimeout(() => {
            if (labelsInput) {
                labelsInput.focus();
                labelsInput.select();
            }
        }, 100);
    }

    close() {
        if (!this.overlay) return;

        this.overlay.style.display = 'none';
        this.callback = null;
        this.currentNodeId = null;
        this.currentLabelMeta = {};

        // 重置状态
        this.hasFinishLabel = false;
        const ratingArea = document.getElementById('finish-rating-area');
        if (ratingArea) ratingArea.style.display = 'none';
        const ratingInput = document.getElementById('finish-rating-input');
        if (ratingInput) ratingInput.value = '';
        const finishResponseInput = document.getElementById('finish-assistant-final-input');
        if (finishResponseInput) finishResponseInput.value = '';

        // Clear input
        const labelsInput = document.getElementById('labels-edit-input');
        if (labelsInput) {
            labelsInput.value = '';
        }
        const needFeedbackArea = document.getElementById('need-feedback-area');
        if (needFeedbackArea) needFeedbackArea.style.display = 'none';
        const needFeedbackQuestionInput = document.getElementById('need-feedback-assistant-question-input');
        const needFeedbackUserFeedbackInput = document.getElementById('need-feedback-user-feedback-input');
        if (needFeedbackQuestionInput) needFeedbackQuestionInput.value = '';
        if (needFeedbackUserFeedbackInput) needFeedbackUserFeedbackInput.value = '';
    }

    save() {
        if (!this.callback) {
            this.close();
            return;
        }

        const labelsInput = document.getElementById('labels-edit-input');
        if (!labelsInput) {
            this.close();
            return;
        }

        const parsedLabels = this.parseLabelsString(labelsInput.value.trim());
        const stripped = this.stripScoreLabels(parsedLabels);
        let labels = stripped.labels;
        labelsInput.value = labels.join(';');

        const hasFinish = labels.includes('FINISH');
        const ratingInput = document.getElementById('finish-rating-input');
        const finishResponseInput = document.getElementById('finish-assistant-final-input');
        const ratingValue = ratingInput ? ratingInput.value.trim() : '';
        let finishScoreValue = null;
        if (hasFinish) {
            const rating = parseInt(ratingValue, 10);
            if (ratingValue === '' || isNaN(rating) || rating < 0 || rating > 100) {
                if (window.showError) {
                    showError("FINISH 标签必须填写 0-100 的评分");
                }
                return;
            }
            finishScoreValue = rating;
        }

        // 构建 label_meta
        const labelMeta = Object.assign({}, this.currentLabelMeta || {});
        const needFeedbackQuestionInput = document.getElementById('need-feedback-assistant-question-input');
        const needFeedbackUserFeedbackInput = document.getElementById('need-feedback-user-feedback-input');
        const needFeedbackQuestion = needFeedbackQuestionInput ? needFeedbackQuestionInput.value.trim() : '';
        const needFeedbackUserFeedback = needFeedbackUserFeedbackInput ? needFeedbackUserFeedbackInput.value.trim() : '';
        if (labels.includes('NEED_FEEDBACK')) {
            labelMeta.NEED_FEEDBACK = {
                assistant_question: needFeedbackQuestion,
                user_feedback: needFeedbackUserFeedback
            };
        } else if (labelMeta.NEED_FEEDBACK) {
            delete labelMeta.NEED_FEEDBACK;
        }

        if (hasFinish) {
            const assistantFinalMessage = finishResponseInput ? finishResponseInput.value.trim() : '';
            labelMeta.FINISH = {
                score: finishScoreValue,
                assistant_final_message: assistantFinalMessage
            };
        } else if (labelMeta.FINISH) {
            delete labelMeta.FINISH;
        }

        // Call the callback with the labels array and label_meta
        this.callback(labels, labelMeta);
        this.close();
    }
}

// Create global instance
window.labelsEditDialog = new LabelsEditDialog();

// Ensure initialization when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (window.labelsEditDialog) {
        window.labelsEditDialog.init();
        console.log('LabelsEditDialog initialized');
    }
});
