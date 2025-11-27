from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Union
from playwright.async_api import async_playwright

router = APIRouter()

class AuditRequest(BaseModel):
    standard: str
    employees: int
    productScopes: List[Union[str, int]]
    processingSteps: List[str]

async def compute_audit_time_logic(standard, employees, product_scopes, processing_steps):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = await browser.new_page(viewport={'width': 1300, 'height': 900})
        
        try:
            await page.goto('https://time-calculator.ifs-certification.com/', wait_until='networkidle', timeout=120000)
            
            # Standard
            await page.wait_for_selector('button[aria-label="Open"]', timeout=30000)
            open_buttons = await page.query_selector_all('button[aria-label="Open"]')
            if open_buttons:
                await open_buttons[0].click()
            
            await page.wait_for_selector('li[role="option"]', timeout=20000)
            
            # Select standard
            found_std = await page.evaluate("""(wanted) => {
                const opts = Array.from(document.querySelectorAll('li[role="option"]'));
                const match = opts.find(li => (li.textContent || '').includes(wanted));
                if (match) { match.click(); return true; }
                return false;
            }""", standard)
            
            if not found_std:
                raise ValueError(f"Standard option not found: {standard}")
                
            # Employees
            await page.wait_for_selector('#numberOfEmployees', timeout=20000)
            await page.click('#numberOfEmployees', click_count=3)
            await page.type('#numberOfEmployees', str(employees), delay=10)
            
            # Helper for clicking labels
            async def click_by_label(val):
                val_str = str(val).strip()
                found = await page.evaluate("""(s) => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    let target = null;
                    
                    // Code match
                    if (/^\\d+$/.test(s)) {
                        target = labels.find(l => (l.textContent || '').trim().startsWith(s + ' '));
                    } else if (/^P\\d+$/i.test(s)) {
                        target = labels.find(l => (l.textContent || '').trim().toUpperCase().startsWith(s.toUpperCase() + ' '));
                    }
                    
                    // Fallback
                    if (!target) {
                        target = labels.find(l => (l.textContent || '').includes(s));
                    }
                    
                    if (target) {
                        target.scrollIntoView({ block: 'center' });
                        target.click();
                        return true;
                    }
                    return false;
                }""", val_str)
                
                if not found:
                    raise ValueError(f"Label not found: {val}")

            # Product Scopes
            for scope in product_scopes:
                await click_by_label(scope)
                
            # Processing Steps
            for step in processing_steps:
                await click_by_label(step)
                
            # Calculate
            await page.wait_for_function("""() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => /calculate/i.test(b.textContent || ''));
                return btn && !btn.hasAttribute('disabled');
            }""", timeout=30000)
            
            clicked_calc = await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => /calculate/i.test(b.textContent || ''));
                if (btn) {
                    btn.scrollIntoView({ block: 'center' });
                    btn.click();
                    return true;
                }
                return false;
            }""")
            
            if not clicked_calc:
                raise ValueError("Calculate button not found")
                
            # Result
            result = await page.wait_for_function("""() => {
                const p = Array.from(document.querySelectorAll('p'))
                    .find(el => /Minimum audit duration:/i.test(el.textContent || ''));
                const span = p?.querySelector('span');
                const txt = (span?.textContent || '').trim();
                if (!txt || txt.startsWith('-') || !/\\d+\\s*hours/i.test(txt)) return null;
                return txt;
            }""", timeout=60000)
            
            return await result.json_value()
            
        finally:
            await browser.close()

@router.post("/audit-time", tags=["Audit"])
async def audit_time(request: AuditRequest):
    try:
        result = await compute_audit_time_logic(
            request.standard,
            request.employees,
            request.productScopes,
            request.processingSteps
        )
        return {"auditDuration": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
