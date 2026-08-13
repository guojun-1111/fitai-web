/* FitAI-web: 客户端健康数据导入 Worker
   支持 ZIP(XML/CSV/JSON) / XML / CSV / JSON
   在独立线程中解析，完成后返回记录数组 */

// Load JSZip for ZIP file support (CDN, self-contained UMD build)
try {
  importScripts('https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js');
} catch (e) {
  // JSZip unavailable — ZIP files will fall back to server-side import
}

// Apple Health Record XML 基础解析（不依赖外部库）
function parseAppleHealthXML(xmlText, platform) {
  var records = [];
  var workouts = [];

  // HK 类型映射
  var typeMap = {
    'HKQuantityTypeIdentifierStepCount': 'steps',
    'HKQuantityTypeIdentifierHeartRate': 'heart_rate',
    'HKQuantityTypeIdentifierRestingHeartRate': 'heart_rate',
    'HKQuantityTypeIdentifierWalkingHeartRateAverage': 'heart_rate',
    'HKCategoryTypeIdentifierSleepAnalysis': 'sleep',
    'HKQuantityTypeIdentifierActiveEnergyBurned': 'calories',
    'HKQuantityTypeIdentifierBasalEnergyBurned': 'calories',
    'HKQuantityTypeIdentifierOxygenSaturation': 'spo2',
    'HKQuantityTypeIdentifierBodyMass': 'weight',
    'HKQuantityTypeIdentifierBodyFatPercentage': 'body_fat'
  };

  // 运动类型映射
  var workoutMap = {
    'HKWorkoutActivityTypeRunning': '跑步', 'HKWorkoutActivityTypeWalking': '走路',
    'HKWorkoutActivityTypeCycling': '骑行', 'HKWorkoutActivityTypeSwimming': '游泳',
    'HKWorkoutActivityTypeHiking': '徒步', 'HKWorkoutActivityTypeYoga': '瑜伽',
    'HKWorkoutActivityTypeTraditionalStrengthTraining': '力量训练',
    'HKWorkoutActivityTypeFunctionalStrengthTraining': '功能性力量训练',
    'HKWorkoutActivityTypeHighIntensityIntervalTraining': 'HIIT',
    'HKWorkoutActivityTypeDance': '舞蹈', 'HKWorkoutActivityTypeElliptical': '椭圆机',
    'HKWorkoutActivityTypeRowing': '划船', 'HKWorkoutActivityTypeStairClimbing': '爬楼',
    'HKWorkoutActivityTypeCrossTraining': '综合训练', 'HKWorkoutActivityTypeMixedCardio': '混合有氧',
    'HKWorkoutActivityTypePilates': '普拉提', 'HKWorkoutActivityTypeTaiChi': '太极'
  };

  // 解析日期
  function parseDate(str) {
    if (!str) return null;
    var m = str.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) return m[1] + '-' + m[2] + '-' + m[3];
    m = str.match(/(\d{4})(\d{2})(\d{2})/);
    if (m) return m[1] + '-' + m[2] + '-' + m[3];
    return null;
  }

  // 提取属性
  function getAttr(tag, name) {
    var re = new RegExp(name + '="([^"]*)"');
    var m = tag.match(re);
    return m ? m[1] : '';
  }

  // 用正则提取所有 Record 和 Workout 元素（不构建 DOM，内存极小）
  var re = /<(Record|Workout)\b[^>]*\/\s*>/g;
  var match;
  while ((match = re.exec(xmlText)) !== null) {
    var tag = match[0];
    if (match[1] === 'Record') {
      var hkType = getAttr(tag, 'type');
      var dt = typeMap[hkType];
      if (!dt) continue;
      var val = parseFloat(getAttr(tag, 'value').replace(',', ''));
      if (!val || val <= 0) continue;
      var startDate = getAttr(tag, 'startDate');
      var dateStr = parseDate(startDate);
      if (!dateStr) continue;

      if (dt === 'sleep') {
        var endDate = getAttr(tag, 'endDate');
        var dur = calcDurationMinutes(startDate, endDate);
        if (dur > 0) val = dur;
        if (val < 30) continue;
      }

      records.push({
        date: dateStr, source_platform: platform || 'apple_health',
        data_type: dt, value: val, unit: getUnit(dt)
      });
    } else { // Workout
      var wtype = getAttr(tag, 'workoutActivityType');
      var name = workoutMap[wtype] || wtype.replace('HKWorkoutActivityType', '');
      if (!name) continue;
      var sdate = parseDate(getAttr(tag, 'startDate'));
      if (!sdate) continue;
      var dur = parseFloat(getAttr(tag, 'duration')) || 0;
      var min = dur > 0 ? Math.round(dur / 60 * 10) / 10 : null;
      workouts.push({ date: sdate, exercise_name: name, duration_minutes: min, source_platform: platform || 'apple_health' });
    }
  }

  return { records: records, workouts: workouts };
}

// 解析 Apple Health CDA XML（简化版，提取 observation 和 organizer）
function parseCDAXML(xmlText, platform) {
  var records = [];

  var displayMap = {
    '步数': 'steps', '心率': 'heart_rate', '睡眠': 'sleep',
    '卡路里': 'calories', '血氧': 'spo2', '体重': 'weight',
    '体脂': 'body_fat', '血压': 'blood_pressure_sys'
  };

  function getAttr(tag, name) {
    var re = new RegExp(name + '="([^"]*)"');
    var m = tag.match(re);
    return m ? m[1] : '';
  }

  function parseDate(str) {
    if (!str) return null;
    var m = str.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) return m[1] + '-' + m[2] + '-' + m[3];
    return null;
  }

  // 提取 observation 元素
  var obsRe = /<observation\b[^>]*>[\s\S]*?<\/observation>/gi;
  var obsMatch;
  while ((obsMatch = obsRe.exec(xmlText)) !== null) {
    var obs = obsMatch[0];
    var code = (obs.match(/code="([^"]+)"/) || [])[1] || '';
    var displayName = (obs.match(/displayName="([^"]+)"/) || [])[1] || '';
    var valStr = (obs.match(/value="([^"]+)"\s+unit/) || [])[1] || '';
    // Try alternative value extraction
    if (!valStr) {
      var vm = obs.match(/<value[^>]*>([\d.]+)<\/value>/);
      if (vm) valStr = vm[1];
    }
    var dateStr = (obs.match(/<effectiveTime[^>]*value="([^"]+)"/) || [])[1] || '';

    if (!valStr || !dateStr) continue;
    var dt = displayMap[displayName] || displayMap[code] || code.toLowerCase();
    if (!dt || dt.length > 30) continue;
    var val = parseFloat(valStr);
    if (!val || val <= 0) continue;
    var d = parseDate(dateStr);
    if (!d) continue;

    records.push({ date: d, source_platform: platform || 'apple_health_cda', data_type: dt, value: val, unit: getUnit(dt) });
  }

  return { records: records, workouts: [] };
}

// 计算两个 ISO 日期的分钟差
function calcDurationMinutes(start, end) {
  try {
    var s = new Date(start), e = new Date(end);
    return Math.round((e - s) / 60000);
  } catch (_) { return 0; }
}

// 单位映射
function getUnit(dt) {
  var units = { steps: 'steps', heart_rate: 'bpm', sleep: 'minutes', calories: 'kcal', spo2: '%', weight: 'kg', body_fat: '%', blood_pressure_sys: 'mmHg', blood_glucose: 'mmol/L' };
  return units[dt] || '';
}

// ========== JSON 解析 ==========
function parseJSON(text, platform) {
  try {
    var data = JSON.parse(text);
    var records = [];
    if (!Array.isArray(data)) data = data.data || data.records || [];
    for (var i = 0; i < data.length; i++) {
      var item = data[i];
      var dt = item.data_type || item.type || '';
      var dateStr = item.date || item.time || '';
      var val = parseFloat(item.value);
      if (dt && dateStr && val > 0) {
        var m = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/);
        if (m) dateStr = m[1] + '-' + m[2] + '-' + m[3];
        records.push({ date: dateStr, source_platform: platform || 'json_import', data_type: dt, value: val, unit: item.unit || getUnit(dt) });
      }
    }
    return { records: records, workouts: [] };
  } catch (e) {
    throw new Error('JSON 解析失败: ' + e.message);
  }
}

// ========== Worker 主逻辑 ==========
self.onmessage = async function(e) {
  var data = e.data;
  try {
    var result = await processFile(data.buffer, data.filename, data.platform || 'local_import');
    self.postMessage({ type: 'done', result: result });
  } catch (err) {
    self.postMessage({ type: 'error', message: err.message || String(err) });
  }
};

async function processFile(buffer, filename, platform) {
  var ext = (filename.split('.').pop() || '').toLowerCase();

  // ZIP 文件
  if (ext === 'zip') {
    return await processZIP(buffer, platform);
  }

  // 文本文件
  var text = new TextDecoder('utf-8').decode(new Uint8Array(buffer));
  var trimmed = text.trim();

  if (ext === 'csv' || ext === 'txt') {
    return parseCSV(trimmed, platform);
  } else if (ext === 'json') {
    return parseJSON(trimmed, platform);
  } else if (ext === 'xml' || trimmed.startsWith('<?xml') || trimmed.startsWith('<HealthData') || trimmed.startsWith('<!DOCTYPE')) {
    if (trimmed.indexOf('<ClinicalDocument') !== -1 || trimmed.indexOf('urn:hl7-org:v3') !== -1) {
      return parseCDAXML(trimmed, platform);
    }
    return parseAppleHealthXML(trimmed, platform);
  } else {
    // 尝试自动检测
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      return parseJSON(trimmed, platform);
    }
    return parseCSV(trimmed, platform);
  }
}

async function processZIP(buffer, platform) {
  if (typeof JSZip === 'undefined') {
    self.postMessage({ type: 'progress', percent: 100, note: 'ZIP will be processed on server' });
    return { records: [], workouts: [] };
  }

  var uint8 = buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : buffer;
  var allRecords = [];
  var allWorkouts = [];

  try {
    var zip = await JSZip.loadAsync(uint8);
    if (zip && zip.files) {
      processZipFiles(zip, platform, allRecords, allWorkouts);
    }
  } catch (e) {
    self.postMessage({ type: 'progress', percent: 100, note: 'ZIP parse failed, using server fallback' });
    return { records: [], workouts: [] };
  }

  self.postMessage({ type: 'progress', percent: 100 });

  return { records: allRecords, workouts: allWorkouts };
}

function processZipFiles(zip, platform, allRecords, allWorkouts) {
  var xmlFiles = [];
  var csvFiles = [];
  var jsonFiles = [];

  Object.keys(zip.files).forEach(function(name) {
    var lower = name.toLowerCase();
    if (lower.endsWith('.xml')) xmlFiles.push(name);
    else if (lower.endsWith('.csv') || lower.endsWith('.txt')) csvFiles.push(name);
    else if (lower.endsWith('.json')) jsonFiles.push(name);
  });

  var totalFiles = xmlFiles.length + csvFiles.length + jsonFiles.length;
  var processed = 0;

  function processOne(name, parser) {
    var content = zip.files[name].asText();
    if (content) {
      var result = parser(content, platform);
      if (result.records) allRecords.push.apply(allRecords, result.records);
      if (result.workouts) allWorkouts.push.apply(allWorkouts, result.workouts);
    }
    processed++;
    self.postMessage({ type: 'progress', percent: Math.round(processed / totalFiles * 100) });
  }

  // 优先处理 XML（最常见的 Apple Health 格式）
  xmlFiles.forEach(function(name) {
    var content = zip.files[name].asText();
    if (content) {
      if (content.indexOf('<ClinicalDocument') !== -1 || content.indexOf('urn:hl7-org:v3') !== -1) {
        processFilesFromContent(content, platform, allRecords, allWorkouts);
      } else {
        processFilesFromContent(content, platform, allRecords, allWorkouts);
      }
    }
    processed++;
    self.postMessage({ type: 'progress', percent: Math.round(processed / Math.max(totalFiles, 1) * 100) });
  });

  csvFiles.forEach(function(name) {
    var content = zip.files[name].asText();
    if (content) {
      var result = parseCSV(content, platform);
      if (result.records) allRecords.push.apply(allRecords, result.records);
    }
    processed++;
    self.postMessage({ type: 'progress', percent: Math.round(processed / Math.max(totalFiles, 1) * 100) });
  });
}

function processFilesFromContent(content, platform, recordsList, workoutsList) {
  var result;
  if (content.indexOf('<ClinicalDocument') !== -1 || content.indexOf('urn:hl7-org:v3') !== -1) {
    result = parseCDAXML(content, platform);
  } else {
    result = parseAppleHealthXML(content, platform);
  }
  if (result.records) recordsList.push.apply(recordsList, result.records);
  if (result.workouts) workoutsList.push.apply(workoutsList, result.workouts);
}

// ========== CSV 解析（简易版，不依赖 Papa Parse） ==========
function parseCSV(text, platform) {
  var records = [];
  var lines = text.split(/\r?\n/);
  if (lines.length < 2) return { records: records, workouts: [] };

  var header = lines[0].split(',').map(function(h) { return h.trim().replace(/"/g, '').toLowerCase(); });

  // 找日期列和数据列
  var dateIdx = -1;
  var colMap = {}; // idx -> data_type

  var dateCols = ['日期', 'date', '时间', 'time', '开始时间', '记录日期'];
  var typeMap = {
    '步数': 'steps', 'steps': 'steps', '心率': 'heart_rate', 'heart_rate': 'heart_rate',
    '睡眠': 'sleep', 'sleep': 'sleep', '卡路里': 'calories', 'calories': 'calories',
    '血氧': 'spo2', 'spo2': 'spo2', '体重': 'weight', 'weight': 'weight',
    '体脂': 'body_fat', 'body_fat': 'body_fat'
  };

  for (var i = 0; i < header.length; i++) {
    var h = header[i];
    if (dateCols.indexOf(h) !== -1) { dateIdx = i; continue; }
    var dt = typeMap[h];
    if (dt) colMap[i] = dt;
  }

  // 扫描数据行
  for (var r = 1; r < lines.length; r++) {
    var cells = lines[r].split(',');
    if (cells.length < 2) continue;

    var dateStr = dateIdx >= 0 ? (cells[dateIdx] || '').trim().replace(/"/g, '') : '';
    var m = dateStr.match(/(\d{4})[-/](\d{2})[-/](\d{2})/);
    if (!m) continue;
    dateStr = m[1] + '-' + m[2] + '-' + m[3];

    Object.keys(colMap).forEach(function(idx) {
      if (idx >= cells.length) return;
      var val = parseFloat((cells[idx] || '').trim().replace(/"/g, '').replace(',', ''));
      if (val && val > 0) {
        var dt = colMap[idx];
        records.push({ date: dateStr, source_platform: platform || 'csv_import', data_type: dt, value: val, unit: getUnit(dt) });
      }
    });
  }

  return { records: records, workouts: [] };
}
