/**
 * EventStr Parser and Generator Utility
 * 用于解析和生成EventStr字符串的工具类
 */
class EventStrParser {
    constructor() {
        // 正则表达式用于解析不同的EventStr格式
        this.patterns = {
            // 通用格式: ClassName(param1=value1, param2=value2, ...)
            general: /^(\w+)\((.*)\)$/,
            
            // 参数解析: key=value 格式，支持嵌套括号和复杂值
            parameter: /(\w+)=([^,]+(?:\([^)]*(?:\([^)]*\))*[^)]*\))*)/g,
            
            // 坐标点格式: (x,y)
            point: /\((-?\d+),(-?\d+)\)/,
            
            // 边界框格式: (left,top,width,height)
            bbox: /\((-?\d+),(-?\d+),(-?\d+),(-?\d+)\)/,
            
            // View信息格式: view=view_str(activity/class-text)
            view: /view=([^(]+)\(([^)]+)\)/,
            
            // View描述符格式: activity/class-text
            viewDescriptor: /^([^/]+)\/([^-]*)-(.*)$/
        };
        
        // 支持的事件类型及其参数定义
        this.eventTypeSchema = {
            'TouchEvent': ['view', 'point', 'bbox'],
            'LongTouchEvent': ['view', 'point', 'bbox', 'duration'],
            'SwipeEvent': ['view', 'start_point', 'start_bbox', 'end_point', 'end_bbox', 'duration'],
            'ScrollEvent': ['view', 'point', 'bbox', 'direction'],
            'SetTextEvent': ['view', 'point', 'bbox', 'text'],
            'PutTextEvent': ['text'],
            'SelectEvent': ['view', 'point', 'bbox'],
            'UnselectEvent': ['view', 'point', 'bbox'],
            'KeyEvent': ['name'],
            'IntentEvent': ['intent'],
            'ManualEvent': ['time'],
            'ExitEvent': [],
            'SpawnEvent': [],
            'KillAppEvent': []
        };
        
        // 事件类型到类名的映射 (UI显示名称到实际类名)
        this.eventTypeMapping = {
            'touch': 'TouchEvent',
            'long_touch': 'LongTouchEvent', 
            'swipe': 'SwipeEvent',
            'scroll': 'ScrollEvent',
            'set_text': 'SetTextEvent',
            'put_text': 'PutTextEvent',
            'select': 'SelectEvent',
            'unselect': 'UnselectEvent',
            'hotkey': 'KeyEvent',
            'intent': 'IntentEvent',
            'manual': 'ManualEvent',
            'exit': 'ExitEvent',
            'spawn': 'SpawnEvent',
            'kill_app': 'KillAppEvent'
        };
    }

    /**
     * 解析EventStr字符串为可编辑的字段对象
     * @param {string} eventStr - 原始EventStr字符串
     * @returns {Object} 解析后的字段对象
     */
    parseEventStr(eventStr) {
        if (!eventStr || typeof eventStr !== 'string') {
            return { error: 'Invalid EventStr' };
        }

        // 匹配主格式 ClassName(parameters)
        const mainMatch = eventStr.match(this.patterns.general);
        if (!mainMatch) {
            return { error: 'Invalid EventStr format' };
        }

        const eventType = mainMatch[1];
        const parameterString = mainMatch[2];

        const result = {
            eventType: eventType,
            original: eventStr,
            fields: {}
        };

        // 如果没有参数，直接返回
        if (!parameterString.trim()) {
            return result;
        }

        // 解析参数
        try {
            const parameters = this.parseParameters(parameterString);
            result.fields = this.structureFields(parameters, eventType);
        } catch (error) {
            result.error = `Parameter parsing error: ${error.message}`;
        }

        return result;
    }

    /**
     * 解析参数字符串
     * @param {string} paramStr - 参数字符串
     * @returns {Object} 参数键值对
     */
    parseParameters(paramStr) {
        const parameters = {};
        
        // 更智能的参数分割，考虑括号嵌套
        const params = this.splitParameters(paramStr);
        
        for (const param of params) {
            const equalIndex = param.indexOf('=');
            if (equalIndex === -1) continue;
            
            const key = param.substring(0, equalIndex).trim();
            let value = param.substring(equalIndex + 1).trim();
            
            // 处理特殊值格式
            if (key === 'view' && value.includes('(')) {
                // 处理view格式: view_str(activity/class-text)
                parameters[key] = this.parseViewValue(value);
            } else if (this.patterns.point.test(value)) {
                // 处理坐标点
                const pointMatch = value.match(this.patterns.point);
                parameters[key] = {
                    type: 'point',
                    x: parseInt(pointMatch[1]),
                    y: parseInt(pointMatch[2])
                };
            } else if (this.patterns.bbox.test(value)) {
                // 处理边界框
                const bboxMatch = value.match(this.patterns.bbox);
                parameters[key] = {
                    type: 'bbox',
                    left: parseInt(bboxMatch[1]),
                    top: parseInt(bboxMatch[2]),
                    width: parseInt(bboxMatch[3]),
                    height: parseInt(bboxMatch[4])
                };
            } else if (!isNaN(value) && !value.includes('(')) {
                // 数字值（但不是括号格式）
                parameters[key] = parseInt(value);
            } else {
                // 字符串值，可能包含不完整的括号表达式
                // 如果是不完整的坐标或bbox，尝试修复
                if ((key.includes('point') || key.includes('bbox')) && value.startsWith('(') && !value.endsWith(')')) {
                    // 不完整的坐标或边界框，标记为需要手动输入
                    if (key.includes('point')) {
                        parameters[key] = {
                            type: 'point',
                            x: 0,
                            y: 0,
                            _incomplete: true,
                            _originalValue: value
                        };
                    } else if (key.includes('bbox')) {
                        parameters[key] = {
                            type: 'bbox',
                            left: 0,
                            top: 0,
                            width: 0,
                            height: 0,
                            _incomplete: true,
                            _originalValue: value
                        };
                    }
                } else {
                    parameters[key] = value;
                }
            }
        }
        
        return parameters;
    }

    /**
     * 智能分割参数，考虑括号嵌套
     * @param {string} paramStr - 参数字符串
     * @returns {Array} 参数数组
     */
    splitParameters(paramStr) {
        const params = [];
        let current = '';
        let parenCount = 0;
        let inQuotes = false;
        
        for (let i = 0; i < paramStr.length; i++) {
            const char = paramStr[i];
            
            if (char === '"' || char === "'") {
                inQuotes = !inQuotes;
            } else if (!inQuotes) {
                if (char === '(') {
                    parenCount++;
                } else if (char === ')') {
                    parenCount--;
                } else if (char === ',' && parenCount === 0) {
                    if (current.trim()) {
                        params.push(current.trim());
                    }
                    current = '';
                    continue;
                }
            }
            
            current += char;
        }
        
        if (current.trim()) {
            params.push(current.trim());
        }
        
        return params;
    }

    /**
     * 解析view值
     * @param {string} viewValue - view值字符串
     * @returns {Object} 解析后的view对象
     */
    parseViewValue(viewValue) {
        const viewMatch = viewValue.match(this.patterns.view);
        if (!viewMatch) {
            return { type: 'view', value: viewValue };
        }

        const viewStr = viewMatch[1];
        const descriptor = viewMatch[2];
        
        const descriptorMatch = descriptor.match(this.patterns.viewDescriptor);
        if (descriptorMatch) {
            return {
                type: 'view',
                viewStr: viewStr,
                activity: descriptorMatch[1],
                className: descriptorMatch[2],
                text: descriptorMatch[3]
            };
        }

        return {
            type: 'view',
            viewStr: viewStr,
            descriptor: descriptor
        };
    }

    /**
     * 根据事件类型结构化字段
     * @param {Object} parameters - 原始参数
     * @param {string} eventType - 事件类型
     * @returns {Object} 结构化的字段
     */
    structureFields(parameters, eventType) {
        const schema = this.eventTypeSchema[eventType] || [];
        const structured = {};

        // 根据schema组织字段
        for (const fieldName of schema) {
            if (parameters.hasOwnProperty(fieldName)) {
                structured[fieldName] = parameters[fieldName];
            }
        }

        // 添加任何不在schema中的额外字段
        for (const [key, value] of Object.entries(parameters)) {
            if (!schema.includes(key)) {
                structured[key] = value;
            }
        }

        return structured;
    }

    /**
     * 根据UI事件类型获取类名
     * @param {string} uiEventType - UI显示的事件类型
     * @returns {string} 实际的类名
     */
    getClassName(uiEventType) {
        return this.eventTypeMapping[uiEventType] || uiEventType;
    }

    /**
     * 将字段对象重新组合成EventStr字符串
     * @param {Object} fields - 字段对象
     * @param {string} eventType - 事件类型 (可以是UI类型或类名)
     * @returns {string} EventStr字符串
     */
    generateEventStr(fields, eventType) {
        if (!eventType) {
            throw new Error('EventType is required');
        }

        // 确保使用正确的类名
        const className = this.getClassName(eventType);
        const parameters = [];
        
        // 按照特定顺序处理字段
        const fieldOrder = this.getFieldOrder(className);
        
        for (const fieldName of fieldOrder) {
            if (fields.hasOwnProperty(fieldName) && fields[fieldName] !== null && fields[fieldName] !== undefined) {
                const value = this.formatFieldValue(fieldName, fields[fieldName]);
                parameters.push(`${fieldName}=${value}`);
            }
        }

        // 添加其他字段
        for (const [key, value] of Object.entries(fields)) {
            if (!fieldOrder.includes(key) && value !== null && value !== undefined) {
                const formattedValue = this.formatFieldValue(key, value);
                parameters.push(`${key}=${formattedValue}`);
            }
        }

        if (parameters.length === 0) {
            return `${className}()`;
        }

        return `${className}(${parameters.join(', ')})`;
    }

    /**
     * 获取字段的显示顺序
     * @param {string} eventType - 事件类型
     * @returns {Array} 字段顺序数组
     */
    getFieldOrder(eventType) {
        const commonOrder = ['view', 'point', 'bbox'];
        const specificOrders = {
            'SwipeEvent': ['view', 'start_point', 'start_bbox', 'end_point', 'end_bbox', 'duration'],
            'LongTouchEvent': ['view', 'point', 'bbox', 'duration'],
            'ScrollEvent': ['view', 'point', 'bbox', 'direction'],
            'SetTextEvent': ['view', 'point', 'bbox', 'text'],
            'KeyEvent': ['name'],
            'IntentEvent': ['intent'],
            'ManualEvent': ['time']
        };

        return specificOrders[eventType] || commonOrder;
    }

    /**
     * 格式化字段值
     * @param {string} fieldName - 字段名
     * @param {*} value - 字段值
     * @returns {string} 格式化后的值
     */
    formatFieldValue(fieldName, value) {
        if (value === null || value === undefined) {
            return 'None';
        }

        if (typeof value === 'object') {
            if (value.type === 'point') {
                // 检查是否有不完整标记，如果有则使用原值
                if (value._incomplete && value._originalValue) {
                    return value._originalValue;
                }
                return `(${value.x},${value.y})`;
            } else if (value.type === 'bbox') {
                // 检查是否有不完整标记，如果有则使用原值
                if (value._incomplete && value._originalValue) {
                    return value._originalValue;
                }
                return `(${value.left},${value.top},${value.width},${value.height})`;
            } else if (value.type === 'view') {
                if (value.viewStr && value.activity && value.className !== undefined && value.text !== undefined) {
                    return `${value.viewStr}(${value.activity}/${value.className}-${value.text})`;
                } else if (value.viewStr && value.descriptor) {
                    return `${value.viewStr}(${value.descriptor})`;
                } else {
                    return value.value || value.viewStr || JSON.stringify(value);
                }
            }
        }

        return value.toString();
    }

    /**
     * 验证字段值
     * @param {string} fieldName - 字段名
     * @param {*} value - 字段值
     * @param {string} eventType - 事件类型
     * @returns {Object} 验证结果 {valid: boolean, error?: string}
     */
    validateField(fieldName, value, eventType) {
        // 基本验证逻辑
        if (fieldName.includes('point') && value && value.type === 'point') {
            if (isNaN(value.x) || isNaN(value.y)) {
                return { valid: false, error: 'Point coordinates must be numbers' };
            }
        }
        
        if (fieldName.includes('bbox') && value && value.type === 'bbox') {
            if (isNaN(value.left) || isNaN(value.top) || isNaN(value.width) || isNaN(value.height)) {
                return { valid: false, error: 'BBox values must be numbers' };
            }
        }

        if (fieldName === 'duration' && value && isNaN(value)) {
            return { valid: false, error: 'Duration must be a number' };
        }

        return { valid: true };
    }
}

// 创建全局实例
window.eventStrParser = new EventStrParser();

// 确保在DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    if (window.eventStrParser) {
        console.log('EventStrParser initialized');
    }
});
