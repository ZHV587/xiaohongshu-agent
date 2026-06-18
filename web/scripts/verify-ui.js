import { chromium } from 'playwright';
import path from 'path';

const ARTIFACT_DIR = 'C:/Users/13387/.gemini/antigravity/brain/1d65899b-954a-4219-964e-579858506e6a';

async function run() {
  console.log('启动 Chromium 浏览器...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  try {
    console.log('访问前端页面 http://127.0.0.1:3200 ...');
    await page.goto('http://127.0.0.1:3200', { waitUntil: 'networkidle' });

    console.log('等待并截取登录首页 (login_page.png)...');
    await page.waitForTimeout(1000);
    const loginPath = path.join(ARTIFACT_DIR, 'login_page.png');
    await page.screenshot({ path: loginPath });
    console.log(`已保存登录页截图: ${loginPath}`);

    console.log('点击 "使用飞书扫码安全登录" 按钮以触发 3D 卡片翻转...');
    await page.click('text=使用飞书扫码安全登录');
    await page.waitForTimeout(1000);

    console.log('点击 "点击模拟扫码" 二维码区域以触发模拟登录...');
    // 使用 hover 触发 group-hover 显示模拟点击遮罩，然后再点击
    await page.hover('text=点击模拟扫码');
    await page.click('text=点击模拟扫码');
    console.log('正在等待授权成功并自动加载工作台...');

    // 授权成功后会有 cookie 刷新并跳转/渲染工作台。等待工作台的主标志性元素加载
    await page.waitForSelector('text=小红书文案智能体', { timeout: 10000 });
    console.log('成功进入工作台！等待页面渲染完毕...');
    await page.waitForTimeout(3000);

    console.log('截取工作台主界面 (workspace_page.png)...');
    const workspacePath = path.join(ARTIFACT_DIR, 'workspace_page.png');
    await page.screenshot({ path: workspacePath });
    console.log(`已保存工作台截图: ${workspacePath}`);

  } catch (err) {
    console.error('自动化测试过程中发生错误:', err);
  } finally {
    await browser.close();
    console.log('浏览器关闭，自动化调试结束。');
  }
}

run();
