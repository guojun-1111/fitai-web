// FitAI 小程序 CI 上传 — npm i miniprogram-ci 后运行 node ci.upload.js
const ci = require('miniprogram-ci');
const path = require('path');

const projectPath = __dirname;
const privateKeyPath = path.join(__dirname, '..', 'private.wxe96ce39f95340ec8.key');

(async () => {
  const project = new ci.Project({
    appid: 'wxe96ce39f95340ec8',
    type: 'miniProgram',
    projectPath: projectPath,
    privateKeyPath: privateKeyPath,
    ignores: ['node_modules/**/*'],
  });

  const version = process.argv[2] || 'v1.0.0';
  const desc = process.argv[3] || 'FitAI 小程序更新';

  console.log(`上传中: ${version} — ${desc}`);
  const result = await ci.upload({
    project,
    version: version,
    desc: desc,
    setting: {
      es6: true,
      minify: true,
    },
    onProgressUpdate: (info) => {
      if (info.status === 'doing') console.log(`  ${info._msg || ''}`);
    },
  });
  console.log('上传成功！版本:', version);
})();
