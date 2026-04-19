class NodeEditor {
    constructor(containerId, utgViewer) {
        this.container = document.getElementById(containerId);
        this.utgViewer = utgViewer;
        this.currentNodeId = null;
        this.currentEditingEdgeId = null;
        this.currentEditingEventStr = null;
        this.isEditingOutgoingEdge = false;
        this.isAddingNewEdge = false;
        this.currentSourceNodeId = null;
    }

    showNodeDetails(nodeId) {
        const node = this.utgViewer.utg.nodes.find(n => n.id === nodeId);
        if (!node) {
            this.showError('未找到节点');
            return;
        }

        this.currentNodeId = nodeId;
        const nodeInfo = this.generateNodeDetailsHTML(node);
        
        // Update sidebar content instead of replacing container
        if (this.container) {
            this.container.innerHTML = nodeInfo;
        }
        
        // No need to update sidebar title since it's not displayed
    }

    //预览图组件
    createEventVisualizationImage(node, width = 270, prefix = 'hover') {
        const nodeId = node.id;
        return `
            <div style="width: ${width}px; margin: 0 auto; position: relative;">
                <img id="${prefix}-img-${nodeId}" 
                    src="${node.image}" 
                    style="width: 100%; height: auto; display: block;" 
                    onload="window.nodeEditor.drawEventVisualizations('${prefix}-img-${nodeId}', '${prefix}-canvas-${nodeId}', '${nodeId}')">
                <canvas id="${prefix}-canvas-${nodeId}" 
                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10;"></canvas>
            </div>
        `;
    }

    //事件绘制
    drawEventVisualizations(imageId, canvasId, nodeId) {
        const img = document.getElementById(imageId);
        const canvas = document.getElementById(canvasId);
        if (!img || !canvas || !nodeId) return;

        //初始化画布
        canvas.width = img.offsetWidth;
        canvas.height = img.offsetHeight;
        const ctx = canvas.getContext('2d');
        const scaleX = img.offsetWidth / (img.naturalWidth || img.offsetWidth);
        const scaleY = img.offsetHeight / (img.naturalHeight || img.offsetHeight);

        //获取事件并绘制
        this.getOutgoingEvents(nodeId).forEach((eventItem, index) => {
            const eventData = this.parseEventString(eventItem.event.event_str);
            if (!eventData) return;
            if (['touch', 'longtouch'].includes(eventData.type)) {
                this.drawTouchVisualization(ctx, eventData, scaleX, scaleY, index + 1);
            } else if (eventData.type === 'swipe') {
                this.drawSwipeVisualization(ctx, eventData, scaleX, scaleY, index + 1);
            }
        });
    }

    //事件文本预览组件（PutText/KeyEvent）
    createEventTextPreview(node, width = 270) {
        const outgoingEvents = this.getOutgoingEvents(node.id);
        //预览配置：类型、正则、默认文本统一管理
        const previewConfigs = [
            {
                type: '文本输入',
                matchPrefix: 'PutText',
                regex: /PutTextEvent\(text=(.*?)\)/,
                defaultText: '未识别文本'
            },
            {
                type: '按键事件',
                matchPrefix: 'KeyEvent',
                regex: /KeyEvent\(name=(.*?)\)/,
                defaultText: '未识别按键'
            }
        ];

        const styles = {
            container: 'clear: both; margin: 8px 0; padding: 6px; background: #f8f9fa; border-radius: 4px; display: flex; align-items: center; gap: 12px;',
            title: 'margin: 0; color: #495057; font-weight: bold; font-size: 8px;',
            content: 'background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-size: 10px; white-space: normal; word-break: break-all; max-width: 100%;'
        };

        let html = '';
        //生成文本预览
        previewConfigs.forEach(config => {
            const filteredEvents = outgoingEvents.filter(item =>
                item.event.event_str?.startsWith(config.matchPrefix)
            );
            if (filteredEvents.length === 0) return;

            let itemHtml = `<div class="${config.type.toLowerCase()}" style="${styles.container}">`;
            itemHtml += `<h5 style="${styles.title}">${config.type}</h5>`;
            itemHtml += '<div style="display: flex; flex-wrap: wrap; gap: 4px; flex: 1;">';
            
            filteredEvents.forEach(event => {
                const match = event.event.event_str.match(config.regex);
                const content = match ? match[1] : config.defaultText;
                itemHtml += `<span style="${styles.content}">${content}</span>`;
            });
            
            itemHtml += '</div></div>';
            html += `<div style="width: ${width}px; margin: 0 auto;">${itemHtml}</div>`;
        });

        return html || `<div style="width: ${width}px; margin: 0 auto; font-size: 8px; color: #666; text-align: center; padding: 4px 0;">暂无文本输入/按键事件</div>`;
    }    
    generateNodeDetailsHTML(node) {
        let stateInfo = "<h2>状态详情</h2><hr/>\n";
        stateInfo += "<div style=\"overflow: hidden;\">";

        // Create a container for the image with event overlays
        stateInfo += "<div class=\"col-md-5\" style=\"float: left; position: relative;\">";
        // stateInfo += `<img id=\"state-image-${node.id}\" src=\"${node.image}\" style=\"width: 100%; height: auto; display: block;\" onload=\"window.nodeEditor.addEventVisualizations('${node.id}')\">`;
        // stateInfo += `<div id=\"event-overlays-${node.id}\" style=\"position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;\"></div>`;
        stateInfo += this.createEventVisualizationImage(node, '100%', 'state'); //复用预览图+画布组件        
        stateInfo += "</div>";

        // 右侧 state_info 信息表格区域采用 col-md-7，float:left 并排。
        // 说明：为防止内容超出无法显示，加了 overflow: auto，以及最大高度限制和强制换行，保证大文本也能被浏览
        stateInfo += `<div class="col-md-7" style="float: left; overflow: auto;">`;
        stateInfo += '<table class="table">\n';
        stateInfo += `<tr><th>包名</th><td style="word-break: break-all; white-space: pre-line;">${node.package}</td></tr>\n`;
        stateInfo += `<tr><th>页面类名</th><td style="word-break: break-all; white-space: pre-line;">${node.activity}</td></tr>\n`;

        // Extract and display labels
        let labelsDisplay = '';
        if (node.label) {
            const labelParts = node.label.split('\n');
            // Filter out the activity name and special markers (<FIRST>, <LAST>)
            const customLabels = labelParts.filter((part, idx) =>
                idx > 0 && part !== '<FIRST>' && part !== '<LAST>' && part.trim() !== ''
            );
            if (customLabels.length > 0) {
                labelsDisplay = customLabels.join('; ');
            }
        }
        stateInfo += `<tr><th>标签</th><td style="word-break: break-all; white-space: pre-line;">${labelsDisplay} <button class=\"btn btn-xs btn-info\" onclick=\"window.nodeEditor.showSetLabelsDialog('${node.id}')\" style=\"margin-left: 8px;\">编辑</button></td></tr>\n`;

        stateInfo += `<tr><th>状态字符串</th><td style="word-break: break-all; white-space: pre-line;">${node.state_str || ''}</td></tr>\n`;
        stateInfo += `<tr><th>结构字符串</th><td style="word-break: break-all; white-space: pre-line;">${node.structure_str || ''}</td></tr>\n`;
        stateInfo += '</table>';

        // Add delete node and delete branch buttons
        stateInfo += "<div style=\"clear: both; margin-top: 15px;\">";
        stateInfo += "<div style=\"display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;\">";
        stateInfo += `<button class=\"btn btn-warning\" onclick=\"window.nodeEditor.deleteNode('${node.id}')\" style=\"flex: 1;\">删除节点</button>`;
        stateInfo += `<button class=\"btn btn-danger\" onclick=\"window.nodeEditor.deleteBranch('${node.id}')\" style=\"flex: 1;\">删除分支</button>`;
        stateInfo += "</div>";
        stateInfo += "</div>";
        stateInfo += "<div style=\"clear: both; margin-top: 8px;\">";
        stateInfo += "<div style=\"display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;\">";
        stateInfo += `<button class=\"btn btn-success\" onclick=\"window.nodeEditor.setFirstState('${node.id}')\" style=\"flex: 1;\">设为开始状态</button>`;
        stateInfo += `<button class=\"btn btn-primary\" onclick=\"window.nodeEditor.setLastState('${node.id}')\" style=\"flex: 1;\">设为结束状态</button>`;
        stateInfo += "</div>";
        stateInfo += "</div>";

        stateInfo += "</div>";
        stateInfo += "</div>";

        stateInfo += "<div style=\"clear: both; margin-top: 15px;\">"; 
        stateInfo += this.createEventTextPreview(node, '100%'); //复用PutText/KeyEvent文本预览组件
        stateInfo += "</div>";        
        // Add outgoing events information
        const outgoingEvents = this.getOutgoingEvents(node.id);

        if (outgoingEvents.length > 0) {
            stateInfo += "<div style=\"clear: both;\"><hr/>";
            stateInfo += "<div style=\"display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;\">";
            stateInfo += `<h4 style=\"margin: 0;\">出边事件（${outgoingEvents.length}）</h4>`;
            stateInfo += `<button class=\"btn btn-sm btn-info\" onclick=\"window.nodeEditor.addNewEvent('${node.id}')\">添加事件</button>`;
            stateInfo += "</div>";
            stateInfo += this.generateOutgoingEventsTable(outgoingEvents);
            stateInfo += "</div>";
        } else {
            stateInfo += "<div style=\"clear: both;\"><hr/>";
            stateInfo += "<div style=\"display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;\">";
            stateInfo += "<h4 style=\"margin: 0;\">无出边事件</h4>";
            stateInfo += `<button class=\"btn btn-sm btn-info\" onclick=\"window.nodeEditor.addNewEvent('${node.id}')\">添加事件</button>`;
            stateInfo += "</div>";
            stateInfo += "</div>";
        }

        // Note: Edit form is now handled by popup dialog

        return stateInfo;
    }

    generateOutgoingEventsTable(outgoingEvents) {
        let tableHTML = "<table class=\"table table-striped\" style=\"table-layout: fixed; word-wrap: break-word;\">";
        tableHTML += "<tr><th style=\"width: 10%;\">序号</th><th style=\"width: 25%;\">目标状态</th><th style=\"width: 45%;\">事件详情</th><th style=\"width: 20%;\">操作</th></tr>";

        for (let i = 0; i < outgoingEvents.length; i++) {
            const eventItem = outgoingEvents[i];
            const targetNode = this.utgViewer.utg.nodes.find(n => n.id === eventItem.to);
            
            tableHTML += "<tr>";
            
            // Add sequence number column
            tableHTML += `<td style=\"text-align: center; font-weight: bold; color: #FF9800;\">${i + 1}</td>`;
            
            tableHTML += "<td style=\"word-wrap: break-word; overflow-wrap: break-word;\">";
            if (targetNode) {
                tableHTML += `<img src=\"${targetNode.image}\" style=\"width: 85%; height: auto; display: block; margin: 2px auto;\" title=\"${targetNode.label || eventItem.to}\">`;
            } else {
                tableHTML += eventItem.to;
            }
            tableHTML += "</td>";

            tableHTML += `<td style=\"word-wrap: break-word; overflow-wrap: break-word;\">${eventItem.event.event_str || ''}</td>`;
            
            tableHTML += "<td>";
            tableHTML += "<div style=\"display: flex; flex-wrap: wrap; gap: 5px; justify-content: center;\">";
            tableHTML += `<button class=\"btn btn-xs btn-info\" onclick=\"window.nodeEditor.editOutgoingEvent('${eventItem.id}')\" style=\"flex: 1;\">编辑</button>`;
            tableHTML += `<button class=\"btn btn-xs btn-danger\" onclick=\"window.nodeEditor.deleteOutgoingEvent('${eventItem.id}')\" style=\"flex: 1;\">删除</button>`;
            tableHTML += "</div>";
            tableHTML += "</td>";
            tableHTML += "</tr>";
        }
        
        tableHTML += "</table>";
        return tableHTML;
    }

    // Form generation is now handled by the popup dialog

    getOutgoingEvents(nodeId) {
        const outgoingEvents = [];

        if (!this.utgViewer.utg || !this.utgViewer.utg.edges) {
            console.log("UTG or UTG.edges is null/undefined");
            return outgoingEvents;
        }

        const numEdges = this.utgViewer.utg.edges.length;
        console.log("Total edges in UTG:", numEdges);
        console.log("Looking for events from node:", nodeId);

        for (let i = 0; i < numEdges; i++) {
            const edge = this.utgViewer.utg.edges[i];
            if (edge.from === nodeId && edge.events && edge.events.length > 0) {
                edge.events.forEach((event, eventIndex) => {
                    console.log("Found matching event:", event);
                    outgoingEvents.push({
                        id: `${edge.id}_${eventIndex}`,
                        edgeId: edge.id,
                        eventIndex: eventIndex,
                        event: event,
                        to: edge.to,
                        from: edge.from
                    });
                });
            }
        }

        // Sort by event_id to match the display order in UTGViewer
        outgoingEvents.sort((a, b) => a.event.event_id - b.event.event_id);

        console.log("Returning", outgoingEvents.length, "outgoing events (sorted by event_id)");
        return outgoingEvents;
    }

    async deleteNode(nodeId) {
        const confirmMessage = `
            <p>确认删除这个节点吗？</p>
            <div class="alert alert-warning">
                <strong>警告：</strong>该节点的所有入边和出边也会被删除，此操作无法撤销。
            </div>
        `;

        // Use custom confirm dialog instead of native confirm
        return new Promise((resolve) => {
            window.confirmDialog.show(confirmMessage, (confirmed) => {
                if (!confirmed) {
                    resolve();
                    return;
                }
                
                // Continue with deletion
                this.performNodeDeletion(nodeId);
                resolve();
            });
        });
    }

    async performNodeDeletion(nodeId) {
        try {
            // Persist deletion to server
            await api.deleteNode(nodeId);

            // Update and refresh the UTG visualization
            await this.utgViewer.loadUTG();

            // Clear the details panel since the node is deleted
            this.container.innerHTML = '<h2>详情</h2><p>节点删除成功。</p>';

            if (window.showSuccess) {
                window.showSuccess('节点及其相关边已成功删除并保存');
            } else {
                alert('节点及其相关边已成功删除并保存');
            }
        } catch (error) {
            console.error('Failed to delete node:', error);
            if (window.showError) {
                window.showError('删除节点失败，请重试');
            } else {
                alert('删除节点失败，请重试');
            }
        }
    }

    async deleteBranch(nodeId) {
        try {
            // First, get the branch states from the server
            const branchData = await api.getBranchStates(nodeId);

            if (!branchData || !branchData.branch_states || branchData.branch_states.length === 0) {
                alert('未找到该节点对应的分支状态。');
                return;
            }

            // Create confirmation dialog with the list of states to be deleted
            // Use the display labels from UTGViewer which includes the node numbers
            // Sort states by their display label number (序号)
            const statesList = branchData.branch_states.map((stateId) => {
                const displayLabel = this.utgViewer.getNodeDisplayLabel(stateId);
                return {
                    stateId: stateId,
                    displayLabel: displayLabel,
                    // Extract the number from display label (format: "序号. 标签")
                    number: parseInt(displayLabel.split('.')[0]) || 0
                };
            })
            .sort((a, b) => a.number - b.number) // Sort by number
            .map(item => `- ${item.displayLabel} (${item.stateId})`)
            .join('\n');

            const confirmMessage = `
                <p>这将删除该分支中的 <strong>${branchData.count}</strong> 个状态：</p>
                <div class="alert alert-info">
                    <pre class="mb-0" style="white-space: pre-wrap; font-family: monospace; background: transparent; padding: 0; max-height: 400px; overflow-y: auto;">${statesList}</pre>
                </div>
                <div class="alert alert-warning">
                    <strong>警告：</strong>此操作无法撤销，确认继续吗？
                </div>
            `;

            // Use custom confirm dialog instead of native confirm
            return new Promise((resolve) => {
                window.confirmDialog.show(confirmMessage, (confirmed) => {
                    if (!confirmed) {
                        resolve();
                        return;
                    }
                    
                    // Continue with deletion
                    this.performBranchDeletion(branchData);
                    resolve();
                });
            });
        } catch (error) {
            console.error('Failed to delete branch:', error);
            const errorMessage = error.message || '删除分支失败，请重试';
            if (window.showError) {
                window.showError(errorMessage);
            } else {
                alert(errorMessage);
            }
        }
    }

    async performBranchDeletion(branchData) {
        try {
            // Show loading indicator
            if (window.showInfo) {
                window.showInfo(`正在删除 ${branchData.count} 个状态...`);
            }

            // Perform batch deletion
            const result = await api.batchDeleteNodes(branchData.branch_states);

            // Update and refresh the UTG visualization
            await this.utgViewer.loadUTG();

            // Clear the details panel
            this.container.innerHTML = '<h2>详情</h2><p>分支删除成功。</p>';

            // Show result message
            let message = `已成功删除 ${result.deleted_nodes.length} 个节点。`;
            if (result.failed_nodes && result.failed_nodes.length > 0) {
                message += `\n\n以下 ${result.failed_nodes.length} 个节点删除失败：\n`;
                message += result.failed_nodes.map(f => `- ${f.node_id}: ${f.reason}`).join('\n');
            }

            if (window.showSuccess) {
                window.showSuccess(message);
            } else {
                alert(message);
            }
        } catch (error) {
            console.error('Failed to perform branch deletion:', error);
            const errorMessage = error.message || '删除分支失败，请重试';
            if (window.showError) {
                window.showError(errorMessage);
            } else {
                alert(errorMessage);
            }
        }
    }

    async deleteOutgoingEvent(eventId) {
        const confirmMessage = `
            <p>确认删除这个事件吗？</p>
            <div class="alert alert-warning">
                <strong>警告：</strong>此操作无法撤销。
            </div>
        `;

        // Use custom confirm dialog instead of native confirm
        return new Promise((resolve) => {
            window.confirmDialog.show(confirmMessage, (confirmed) => {
                if (!confirmed) {
                    resolve();
                    return;
                }

                // Continue with deletion
                this.performEventDeletion(eventId);
                resolve();
            });
        });
    }

    async performEventDeletion(eventId) {
        try {
            // Get the currently selected node before updating data
            const selectedNodes = this.utgViewer.network.getSelectedNodes();
            const currentNodeId = selectedNodes.length > 0 ? selectedNodes[0] : null;
            
            // Find the event to get the edge ID and event_str
            const eventItem = this.getOutgoingEvents(this.currentNodeId).find(e => e.id === eventId);
            if (!eventItem) {
                alert('未找到事件');
                return;
            }
            
            // Use the new delete event API to delete only the specific event
            await api.deleteEvent(eventItem.edgeId, eventItem.event.event_str);

            // Update and refresh the UTG visualization
            await this.utgViewer.loadUTG();
            
            // Re-select the same node and refresh the details panel
            if (currentNodeId) {
                // Use setTimeout to ensure the network has finished updating
                setTimeout(() => {
                    this.utgViewer.network.selectNodes([currentNodeId]);
                    this.showNodeDetails(currentNodeId);
                }, 100);
            }
            
            if (window.showSuccess) {
                window.showSuccess('事件已成功删除并保存');
            } else {
                alert('事件已成功删除并保存');
            }
        } catch (error) {
            console.error('Failed to delete event:', error);
            if (window.showError) {
                window.showError('删除失败，请重试');
            } else {
                alert('删除失败，请重试');
            }
        }
    }

    editOutgoingEvent(eventId) {
        const eventItem = this.getOutgoingEvents(this.currentNodeId).find(e => e.id === eventId);

        if (!eventItem) {
            alert('未找到指定事件');
            return;
        }

        // Store the current editing event ID and set flag
        this.currentEditingEdgeId = eventItem.edgeId;
        this.isEditingOutgoingEdge = true;
        this.isAddingNewEdge = false;

        // Store the original event string for identification
        this.currentEditingEventStr = eventItem.event.event_str;

        // Open popup dialog for editing
        window.eventEditDialog.openForNodeEditing({
            isAddingNewEdge: false,
            showFromState: true,
            nodes: this.utgViewer.utg.nodes,
            fromState: eventItem.from,
            targetState: eventItem.to,
            eventType: eventItem.event.event_type || 'touch',
            eventStr: eventItem.event.event_str || '',
            onSave: async (formData) => {
                // 统一使用 updateEvent API，支持状态改变
                // 如果状态改变了，传入新状态；否则传入 null
                const newFromState = formData.fromState !== eventItem.from ? formData.fromState : null;
                const newToState = formData.targetState !== eventItem.to ? formData.targetState : null;

                await api.updateEvent(
                    this.currentEditingEdgeId,
                    this.currentEditingEventStr,
                    formData.eventType,
                    formData.eventStr,
                    newFromState,
                    newToState
                );

                // Update and refresh the UTG visualization
                await this.utgViewer.loadUTG();

                // Refresh the node details
                if (this.currentNodeId) {
                    setTimeout(() => {
                        this.utgViewer.network.selectNodes([this.currentNodeId]);
                        this.showNodeDetails(this.currentNodeId);
                    }, 100);
                }

                if (window.showSuccess) {
                    window.showSuccess('事件更新成功');
                } else {
                    alert('事件更新成功');
                }
            }
        });
    }

    addNewEvent(sourceNodeId) {
        // Set flags for adding new event
        this.isAddingNewEdge = true;
        this.isEditingOutgoingEdge = false;
        this.currentSourceNodeId = sourceNodeId;
        this.currentEditingEdgeId = null;

        // Open popup dialog for adding new event
        window.eventEditDialog.openForNodeEditing({
            isAddingNewEdge: true,
            showFromState: true,
            nodes: this.utgViewer.utg.nodes,
            fromState: sourceNodeId,
            targetState: null,
            eventType: 'touch',
            eventStr: '',
            onSave: async (formData) => {
                await api.createEvent(this.currentSourceNodeId, formData.targetState, formData.eventType, formData.eventStr);

                // Update and refresh the UTG visualization
                await this.utgViewer.loadUTG();
                
                // Refresh the node details
                if (this.currentNodeId) {
                    setTimeout(() => {
                        this.utgViewer.network.selectNodes([this.currentNodeId]);
                        this.showNodeDetails(this.currentNodeId);
                    }, 100);
                }
                
                if (window.showSuccess) {
                    window.showSuccess('新事件创建成功');
                } else {
                    alert('新事件创建成功');
                }
            }
        });
    }

    // Form handling is now done by the popup dialog

    // Save handling is now done by the popup dialog

    cancelEventEdit() {
        // Reset flags
        this.currentEditingEdgeId = null;
        this.currentEditingEventStr = null;
        this.isEditingOutgoingEdge = false;
        this.isAddingNewEdge = false;
        this.currentSourceNodeId = null;
    }

    addEventVisualizations(nodeId) {
        const overlayContainer = document.getElementById(`event-overlays-${nodeId}`);
        const stateImage = document.getElementById(`state-image-${nodeId}`);
        
        if (!overlayContainer || !stateImage) return;
        
        // Clear any existing overlays
        overlayContainer.innerHTML = '';
        
        // Get outgoing events for this node
        const outgoingEvents = this.getOutgoingEvents(nodeId);
        console.log(`Adding event visualizations for node ${nodeId}, found ${outgoingEvents.length} outgoing events`);
        
        // Function to draw overlays when image is ready
        const drawWhenReady = () => {
            // Wait a small amount for layout to stabilize
            setTimeout(() => {
                this.drawEventOverlays(overlayContainer, stateImage, outgoingEvents);
            }, 10);
        };
        
        // Wait for image to load before drawing overlays
        if (stateImage.complete && stateImage.naturalHeight !== 0) {
            drawWhenReady();
        } else {
            stateImage.onload = drawWhenReady;
        }
    }

    drawEventOverlays(overlayContainer, stateImage, outgoingEvents) {
        console.log('Drawing event overlays:', {
            overlayContainer,
            stateImage: {
                src: stateImage.src,
                width: stateImage.offsetWidth,
                height: stateImage.offsetHeight,
                naturalWidth: stateImage.naturalWidth,
                naturalHeight: stateImage.naturalHeight,
                complete: stateImage.complete
            },
            eventCount: outgoingEvents.length
        });
        
        outgoingEvents.forEach((eventItem, index) => {
            console.log(`Processing event ${index + 1}:`, eventItem);
            
            const event = eventItem.event;
            console.log(`Event ${index + 1} details:`, event);
            
            const eventData = this.parseEventString(event.event_str);
            
            if (eventData) {
                console.log(`Creating visualization for event ${index + 1}:`, eventData);
                this.createEventVisualization(overlayContainer, eventData, index + 1, stateImage);
            } else {
                console.log(`Event ${index + 1}: Failed to parse event data`);
            }
        });
    }

    parseEventString(eventStr) {
        if (!eventStr) return null;
        
        console.log('Parsing event string with EventStrParser:', eventStr);
        
        // Use the EventStrParser utility
        if (!window.eventStrParser) {
            console.warn('EventStrParser not available');
            return null;
        }
        
        try {
            const parsed = window.eventStrParser.parseEventStr(eventStr);
            
            if (parsed.error) {
                console.warn('EventStrParser error:', parsed.error);
                return null;
            }
            
            console.log('EventStrParser result:', parsed);
            
            // Convert to visualization format
            return this.convertToVisualizationFormat(parsed);
        } catch (error) {
            console.warn('Failed to parse with EventStrParser:', error);
            return null;
        }
    }

    convertToVisualizationFormat(parsed) {
        if (!parsed || !parsed.eventType || !parsed.fields) {
            return null;
        }

        const eventType = parsed.eventType;
        const fields = parsed.fields;
        
        if (eventType === 'TouchEvent') {
            const result = {
                type: 'touch'
            };
            
            // Extract point coordinates
            if (fields.point && fields.point.type === 'point') {
                result.x = fields.point.x;
                result.y = fields.point.y;
            }
            
            // Extract bounding box
            if (fields.bbox && fields.bbox.type === 'bbox') {
                result.bbox = {
                    x1: fields.bbox.left,
                    y1: fields.bbox.top,
                    x2: fields.bbox.left + fields.bbox.width,
                    y2: fields.bbox.top + fields.bbox.height
                };
            }
            
            console.log('Converted TouchEvent:', result);
            return result;
        }
        
        if (eventType === 'SwipeEvent') {
            const result = {
                type: 'swipe'
            };
            
            // Extract start point
            if (fields.start_point && fields.start_point.type === 'point') {
                result.startX = fields.start_point.x;
                result.startY = fields.start_point.y;
            }
            
            // Extract end point
            if (fields.end_point && fields.end_point.type === 'point') {
                result.endX = fields.end_point.x;
                result.endY = fields.end_point.y;
            }

            //提取start_bbox
            if (fields.start_bbox && fields.start_bbox.type === 'bbox') {
                result.startBbox = {
                    x1: fields.start_bbox.left,
                    y1: fields.start_bbox.top,
                    x2: fields.start_bbox.left + fields.start_bbox.width,
                    y2: fields.start_bbox.top + fields.start_bbox.height
                };
            }

            //提取end_bbox
            if (fields.end_bbox && fields.end_bbox.type === 'bbox') {
                result.endBbox = {
                    x1: fields.end_bbox.left,
                    y1: fields.end_bbox.top,
                    x2: fields.end_bbox.left + fields.end_bbox.width,
                    y2: fields.end_bbox.top + fields.end_bbox.height
                };
            }            
            console.log('Converted SwipeEvent:', result);
            return result;
        }
        
        //LongTouchEvent处理
        if (eventType === 'LongTouchEvent') {
            const result = {
                type: 'longtouch' 
            };
            
            //提取点击坐标（与TouchEvent一致）
            if (fields.point && fields.point.type === 'point') {
                result.x = fields.point.x;
                result.y = fields.point.y;
            }
            
            //提取bbox（与TouchEvent一致）
            if (fields.bbox && fields.bbox.type === 'bbox') {
                result.bbox = {
                    x1: fields.bbox.left,
                    y1: fields.bbox.top,
                    x2: fields.bbox.left + fields.bbox.width,
                    y2: fields.bbox.top + fields.bbox.height
                };
            }
            console.log('Converted LongTouchEvent:', result);
            return result;
        }        
        console.log('Unsupported event type for visualization:', eventType);
        return null;
    }


    createEventVisualization(overlayContainer, eventData, edgeNumber, stateImage) {
        console.log('Creating event visualization:', { eventData, edgeNumber });
        
        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '10';
        
        overlayContainer.appendChild(canvas);
        
        // Get the actual rendered dimensions and position of the image
        const imageRect = stateImage.getBoundingClientRect();
        const containerRect = overlayContainer.getBoundingClientRect();
        
        // Calculate the image's position relative to the container
        const imageOffsetX = imageRect.left - containerRect.left;
        const imageOffsetY = imageRect.top - containerRect.top;
        
        // Get the actual displayed size of the image
        const displayedWidth = stateImage.offsetWidth;
        const displayedHeight = stateImage.offsetHeight;
        
        // Position and size the canvas to exactly match the image
        canvas.style.left = imageOffsetX + 'px';
        canvas.style.top = imageOffsetY + 'px';
        canvas.style.width = displayedWidth + 'px';
        canvas.style.height = displayedHeight + 'px';
        
        // Set canvas resolution to match the displayed size
        canvas.width = displayedWidth;
        canvas.height = displayedHeight;
        
        console.log('Canvas created:', {
            canvasWidth: canvas.width,
            canvasHeight: canvas.height,
            imageOffsetX,
            imageOffsetY,
            displayedWidth,
            displayedHeight,
            imageNaturalWidth: stateImage.naturalWidth,
            imageNaturalHeight: stateImage.naturalHeight
        });
        
        const ctx = canvas.getContext('2d');
        
        // Calculate scale factors based on the image's natural size vs displayed size
        const scaleX = displayedWidth / (stateImage.naturalWidth || displayedWidth);
        const scaleY = displayedHeight / (stateImage.naturalHeight || displayedHeight);
        
        console.log('Scale factors:', { scaleX, scaleY });
        
        if (eventData.type === 'touch') {
            console.log('Drawing touch visualization');
            this.drawTouchVisualization(ctx, eventData, scaleX, scaleY, edgeNumber);
        } else if (eventData.type === 'swipe') {
            console.log('Drawing swipe visualization');
            this.drawSwipeVisualization(ctx, eventData, scaleX, scaleY, edgeNumber);
        }else if (eventData.type === 'longtouch') {
            console.log('Drawing long touch visualization');
            this.drawTouchVisualization(ctx, eventData, scaleX, scaleY, edgeNumber);
        }         
    }

    drawTouchVisualization(ctx, eventData, scaleX, scaleY, edgeNumber) {
        const x = eventData.x * scaleX;
        const y = eventData.y * scaleY;
        
        // Draw bounding box if available
        if (eventData.bbox) {
            const bbox = eventData.bbox;
            const bboxX = bbox.x1 * scaleX;
            const bboxY = bbox.y1 * scaleY;
            const bboxWidth = (bbox.x2 - bbox.x1) * scaleX;
            const bboxHeight = (bbox.y2 - bbox.y1) * scaleY;
            
            // Draw bounding box
            ctx.strokeStyle = '#2196F3';
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.strokeRect(bboxX, bboxY, bboxWidth, bboxHeight);
            ctx.setLineDash([]);
            
            // Fill with semi-transparent blue
            ctx.fillStyle = 'rgba(33, 150, 243, 0.2)';
            ctx.fillRect(bboxX, bboxY, bboxWidth, bboxHeight);
        }
        
        // Draw touch point as hollow circle (ring)
        ctx.strokeStyle = '#FF5722';
        ctx.lineWidth = 3;
        ctx.beginPath();
        const touch_radius = Math.max(5, Math.min(15, Math.min(ctx.canvas.width, ctx.canvas.height) * 0.008));
        ctx.arc(x, y, touch_radius, 0, 2 * Math.PI);
        ctx.stroke();
        
        // Calculate smart position for edge number to avoid edges
        const numberOffsetX = 15;
        const numberOffsetY = 10;
        // Dynamically adjust radius based on canvas size
        const radius = Math.max(8, Math.min(20, Math.min(ctx.canvas.width, ctx.canvas.height) * 0.012));
        let numberX = x + numberOffsetX;
        let numberY = y - numberOffsetY;
        
        // If the preferred position would be out of bounds, try alternative positions
        if (x + numberOffsetX + radius > ctx.canvas.width && x - numberOffsetX - radius > 0){
            // left side
            numberX = x - numberOffsetX;
        }
        

        if (y - numberOffsetY - radius  < 0 && y + numberOffsetY + radius < ctx.canvas.height) {
            // bottom side
            numberY = y + numberOffsetY;    
        }
        
        this.drawEventNumber(ctx, numberX, numberY, edgeNumber);
    }

    drawSwipeVisualization(ctx, eventData, scaleX, scaleY, edgeNumber) {
        const startX = eventData.startX * scaleX;
        const startY = eventData.startY * scaleY;
        const endX = eventData.endX * scaleX;
        const endY = eventData.endY * scaleY;
        
        console.log('Drawing swipe visualization:', {
            coordinates: { startX: eventData.startX, startY: eventData.startY, endX: eventData.endX, endY: eventData.endY },
            scaled: { startX, startY, endX, endY },
            startBbox: eventData.startBbox,
            endBbox: eventData.endBbox            
        });
        //绘制 start_bbox
        if (eventData.startBbox) {
            const bbox = eventData.startBbox;
            const bboxX = bbox.x1 * scaleX;
            const bboxY = bbox.y1 * scaleY;
            const bboxWidth = (bbox.x2 - bbox.x1) * scaleX;
            const bboxHeight = (bbox.y2 - bbox.y1) * scaleY;
            
            // 绘制虚线边框
            ctx.strokeStyle = '#4CAF50';
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.strokeRect(bboxX, bboxY, bboxWidth, bboxHeight);
            ctx.setLineDash([]);
            
            // 绘制半透填充
            ctx.fillStyle = 'rgba(76, 175, 80, 0.2)';
            ctx.fillRect(bboxX, bboxY, bboxWidth, bboxHeight);
        }

        //绘制end_bbox
        if (eventData.endBbox) {
            const bbox = eventData.endBbox;
            const bboxX = bbox.x1 * scaleX;
            const bboxY = bbox.y1 * scaleY;
            const bboxWidth = (bbox.x2 - bbox.x1) * scaleX;
            const bboxHeight = (bbox.y2 - bbox.y1) * scaleY;
            
            // 绘制虚线边框
            ctx.strokeStyle = '#FF5722'; 
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.strokeRect(bboxX, bboxY, bboxWidth, bboxHeight);
            ctx.setLineDash([]);
            
            // 绘制半透填充
            ctx.fillStyle = 'rgba(255, 87, 34, 0.2)';
            ctx.fillRect(bboxX, bboxY, bboxWidth, bboxHeight);
        }        

        // Draw swipe line
        ctx.strokeStyle = '#4CAF50';
        ctx.lineWidth = 4;
        ctx.lineCap = 'round';
        ctx.setLineDash([8, 4]);
        
        ctx.beginPath();
        ctx.moveTo(startX, startY);
        ctx.lineTo(endX, endY);
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Draw arrow at end point
        const angle = Math.atan2(endY - startY, endX - startX);
        const arrowLength = 20;
        const arrowAngle = Math.PI / 6;
        
        ctx.strokeStyle = '#4CAF50';
        ctx.lineWidth = 4;
        ctx.lineCap = 'round';
        
        ctx.beginPath();
        ctx.moveTo(endX, endY);
        ctx.lineTo(
            endX - arrowLength * Math.cos(angle - arrowAngle),
            endY - arrowLength * Math.sin(angle - arrowAngle)
        );
        ctx.moveTo(endX, endY);
        ctx.lineTo(
            endX - arrowLength * Math.cos(angle + arrowAngle),
            endY - arrowLength * Math.sin(angle + arrowAngle)
        );
        ctx.stroke();
        
        // Calculate smart position for edge number at midpoint
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        
        const numberOffsetX = 15;
        const numberOffsetY = -10;
        let numberX = midX + numberOffsetX;
        let numberY = midY + numberOffsetY;
        
        // If the preferred position would be out of bounds, try alternative positions
        // Dynamically adjust radius based on canvas size
        const radius = Math.max(8, Math.min(20, Math.min(ctx.canvas.width, ctx.canvas.height) * 0.012));
        if (numberX + radius > ctx.canvas.width || numberY - radius < 0) {
            // Try left side
            numberX = midX - numberOffsetX;
            numberY = midY + Math.abs(numberOffsetY);
            
            // If still out of bounds, try bottom
            if (numberX - radius < 0) {
                numberX = midX;
                numberY = midY + numberOffsetX;
            }
        }
        
        this.drawEventNumber(ctx, numberX, numberY, edgeNumber);
    }

    drawEventNumber(ctx, x, y, eventNumber) {
        // Ensure the event number stays within canvas bounds
        // Dynamically adjust radius based on canvas size
        const canvasWidth = ctx.canvas.width;
        const canvasHeight = ctx.canvas.height;
        const radius = Math.max(8, Math.min(20, Math.min(canvasWidth, canvasHeight) * 0.012));
        
        // Clamp coordinates to keep the circle within bounds
        x = Math.max(radius, Math.min(canvasWidth - radius, x));
        y = Math.max(radius, Math.min(canvasHeight - radius, y));
        
        // Draw background circle
        ctx.fillStyle = '#FF9800';
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, 2 * Math.PI);
        ctx.fill();
        
        // Draw border
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Draw number
        ctx.fillStyle = '#FFFFFF';
        // Dynamically adjust font size based on radius
        const fontSize = Math.round(radius * 1.0);
        ctx.font = `bold ${fontSize}px Arial`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(eventNumber.toString(), x, y);
    }

    async setFirstState(nodeId) {
        try {
            // Call API to set this node as the first state
            await api.setFirstState(nodeId);

            // Update and refresh the UTG visualization
            await this.utgViewer.loadUTG();

            // Refresh node details
            if (this.currentNodeId) {
                setTimeout(() => {
                    this.utgViewer.network.selectNodes([this.currentNodeId]);
                    this.showNodeDetails(this.currentNodeId);
                }, 100);
            }

            if (window.showSuccess) {
                window.showSuccess('已成功设为首状态');
            } else {
                alert('已成功设为首状态');
            }
        } catch (error) {
            console.error('Failed to set first state:', error);
            if (window.showError) {
                window.showError('设为首状态失败，请重试');
            } else {
                alert('设为首状态失败，请重试');
            }
        }
    }

    async setLastState(nodeId) {
        try {
            // Call API to set this node as the last state
            await api.setLastState(nodeId);

            // Update and refresh the UTG visualization
            await this.utgViewer.loadUTG();

            // Refresh node details
            if (this.currentNodeId) {
                setTimeout(() => {
                    this.utgViewer.network.selectNodes([this.currentNodeId]);
                    this.showNodeDetails(this.currentNodeId);
                }, 100);
            }

            if (window.showSuccess) {
                window.showSuccess('已成功设为末状态');
            } else {
                alert('已成功设为末状态');
            }
        } catch (error) {
            console.error('Failed to set last state:', error);
            if (window.showError) {
                window.showError('设为末状态失败，请重试');
            } else {
                alert('设为末状态失败，请重试');
            }
        }
    }

    showSetLabelsDialog(nodeId) {
        // Get current node to check existing labels
        const node = this.utgViewer.utg.nodes.find(n => n.id === nodeId);
        let currentLabels = '';

        if (node && node.label) {
            // Parse existing labels from the label string
            // Label format: "short_activity_name\nlabel1\nlabel2\n<FIRST>\n<LAST>"
            const labelParts = node.label.split('\n');
            // Filter out the activity name and special markers (<FIRST>, <LAST>)
            const customLabels = labelParts.filter((part, idx) =>
                idx > 0 && part !== '<FIRST>' && part !== '<LAST>' && part.trim() !== ''
            );
            currentLabels = customLabels.join(';');
        }

        const currentLabelMeta = (node && node.label_meta) ? node.label_meta : {};

        // Use the new labels edit dialog
        window.labelsEditDialog.show(nodeId, currentLabels, currentLabelMeta, async (labels, labelMeta) => {
            try {
                await api.setNodeLabels(nodeId, labels, labelMeta);

                // Update and refresh the UTG visualization
                await this.utgViewer.loadUTG();

                // Refresh node details
                if (this.currentNodeId) {
                    setTimeout(() => {
                        this.utgViewer.network.selectNodes([this.currentNodeId]);
                        this.showNodeDetails(this.currentNodeId);
                    }, 100);
                }

                if (window.showSuccess) {
                    window.showSuccess('标签更新成功');
                } else {
                    alert('标签更新成功');
                }
            } catch (error) {
                console.error('Failed to edit labels:', error);
                if (window.showError) {
                    window.showError('编辑标签失败，请重试');
                } else {
                    alert('编辑标签失败，请重试');
                }
            }
        });
    }

    showError(message) {
        this.container.innerHTML = `<h2>错误</h2><p>${message}</p>`;
    }
}
