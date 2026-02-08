from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone
import io
import xlsxwriter

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', '')
db_name = os.environ.get('DB_NAME', 'presupuesto_familiar')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Create the main app
app = FastAPI(title="Presupuesto Familiar API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
class FamilyMember(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    percentage: float = 50.0

class ExpenseCategory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    icon: str = "folder"
    color: str = "#3b82f6"

class BankAccount(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: str = "checking"
    color: str = "#3b82f6"

class ExpenseItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    budget: float = 0
    actual: float = 0
    category_id: Optional[str] = None

class FamilyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    members: List[FamilyMember] = []
    categories: List[ExpenseCategory] = []
    bank_accounts: List[BankAccount] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MonthData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    year: int
    month: int
    month_name: str
    income: Dict[str, float] = {}
    fixed_expenses: List[ExpenseItem] = []
    variable_expenses: List[ExpenseItem] = []
    category_expenses: Dict[str, List[ExpenseItem]] = {}
    bank_balances: Dict[str, float] = {}
    savings: Dict[str, float] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MonthDataCreate(BaseModel):
    year: int
    month: int
    month_name: str
    income: Dict[str, float] = {}
    fixed_expenses: List[ExpenseItem] = []
    variable_expenses: List[ExpenseItem] = []
    category_expenses: Dict[str, List[ExpenseItem]] = {}
    savings: Dict[str, float] = {}

class MonthDataUpdate(BaseModel):
    income: Optional[Dict[str, float]] = None
    fixed_expenses: Optional[List[ExpenseItem]] = None
    variable_expenses: Optional[List[ExpenseItem]] = None
    category_expenses: Optional[Dict[str, List[ExpenseItem]]] = None
    bank_balances: Optional[Dict[str, float]] = None
    savings: Optional[Dict[str, float]] = None

# Routes
@api_router.get("/")
async def root():
    return {"message": "Budget Familiar API"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# Family Config Routes
@api_router.get("/family-config")
async def get_family_config():
    config = await db.family_config.find_one({}, {"_id": 0})
    if not config:
        default_config = {
            "id": str(uuid.uuid4()),
            "members": [
                {"id": str(uuid.uuid4()), "name": "Nata", "percentage": 52.0},
                {"id": str(uuid.uuid4()), "name": "Jon", "percentage": 48.0}
            ],
            "categories": [
                {"id": str(uuid.uuid4()), "name": "Niños", "icon": "baby", "color": "#ec4899"},
                {"id": str(uuid.uuid4()), "name": "Casa", "icon": "home", "color": "#3b82f6"},
                {"id": str(uuid.uuid4()), "name": "Transporte", "icon": "car", "color": "#f59e0b"},
                {"id": str(uuid.uuid4()), "name": "Entretenimiento", "icon": "gamepad", "color": "#8b5cf6"}
            ],
            "bank_accounts": [
                {"id": str(uuid.uuid4()), "name": "Cuenta Principal", "type": "checking", "color": "#3b82f6"},
                {"id": str(uuid.uuid4()), "name": "Ahorros", "type": "savings", "color": "#10b981"}
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.family_config.insert_one(default_config)
        return default_config
    return config

@api_router.put("/family-config")
async def update_family_config(members: List[dict] = None, categories: List[dict] = None, bank_accounts: List[dict] = None):
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if members is not None:
        total = sum(m.get("percentage", 0) for m in members)
        if abs(total - 100) > 0.1:
            raise HTTPException(status_code=400, detail=f"Los porcentajes deben sumar 100% (actual: {total}%)")
        update_data["members"] = members
    
    if categories is not None:
        update_data["categories"] = categories
    
    if bank_accounts is not None:
        update_data["bank_accounts"] = bank_accounts
    
    await db.family_config.update_one({}, {"$set": update_data}, upsert=True)
    return await get_family_config()

@api_router.post("/family-config/member")
async def add_family_member(name: str, percentage: float):
    config = await get_family_config()
    new_member = {"id": str(uuid.uuid4()), "name": name, "percentage": percentage}
    members = config.get("members", [])
    members.append(new_member)
    await db.family_config.update_one({}, {"$set": {"members": members, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return new_member

@api_router.delete("/family-config/member/{member_id}")
async def delete_family_member(member_id: str):
    config = await get_family_config()
    members = [m for m in config.get("members", []) if m.get("id") != member_id]
    await db.family_config.update_one({}, {"$set": {"members": members, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Member deleted"}

@api_router.post("/family-config/category")
async def add_category(name: str, icon: str = "folder", color: str = "#3b82f6"):
    config = await get_family_config()
    new_category = {"id": str(uuid.uuid4()), "name": name, "icon": icon, "color": color}
    categories = config.get("categories", [])
    categories.append(new_category)
    await db.family_config.update_one({}, {"$set": {"categories": categories, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return new_category

@api_router.delete("/family-config/category/{category_id}")
async def delete_category(category_id: str):
    config = await get_family_config()
    categories = [c for c in config.get("categories", []) if c.get("id") != category_id]
    await db.family_config.update_one({}, {"$set": {"categories": categories, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Category deleted"}

# Month Routes
@api_router.get("/months")
async def get_all_months():
    months = await db.budget_months.find({}, {"_id": 0}).sort([("year", 1), ("month", 1)]).to_list(1000)
    return months

@api_router.get("/months/{year}/{month}")
async def get_month(year: int, month: int):
    month_data = await db.budget_months.find_one({"year": year, "month": month}, {"_id": 0})
    if not month_data:
        raise HTTPException(status_code=404, detail="Month not found")
    return month_data

@api_router.post("/months")
async def create_month(data: MonthDataCreate):
    existing = await db.budget_months.find_one({"year": data.year, "month": data.month})
    if existing:
        raise HTTPException(status_code=400, detail="Month already exists")
    
    month_obj = MonthData(**data.model_dump())
    doc = month_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    
    await db.budget_months.insert_one(doc)
    return month_obj

@api_router.put("/months/{year}/{month}")
async def update_month(year: int, month: int, data: MonthDataUpdate):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.budget_months.update_one({"year": year, "month": month}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Month not found")
    
    return await db.budget_months.find_one({"year": year, "month": month}, {"_id": 0})

@api_router.delete("/months/{year}/{month}")
async def delete_month(year: int, month: int):
    result = await db.budget_months.delete_one({"year": year, "month": month})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Month not found")
    return {"message": "Month deleted successfully"}

@api_router.get("/annual-summary/{year}")
async def get_annual_summary(year: int):
    months = await db.budget_months.find({"year": year}, {"_id": 0}).sort("month", 1).to_list(12)
    config = await get_family_config()
    
    if not months:
        raise HTTPException(status_code=404, detail="No data for this year")
    
    total_income = 0
    total_expenses = 0
    expense_by_category = {}
    monthly_summaries = []
    member_contributions = {m["name"]: 0 for m in config.get("members", [])}
    
    for m in months:
        month_income = sum(m.get("income", {}).values())
        month_fixed = sum(e.get("actual", 0) for e in m.get("fixed_expenses", []))
        month_variable = sum(e.get("actual", 0) for e in m.get("variable_expenses", []))
        
        month_category = 0
        for cat_id, expenses in m.get("category_expenses", {}).items():
            cat_total = sum(e.get("actual", 0) for e in expenses)
            month_category += cat_total
            cat_name = next((c["name"] for c in config.get("categories", []) if c["id"] == cat_id), "Otros")
            expense_by_category[cat_name] = expense_by_category.get(cat_name, 0) + cat_total
        
        month_expenses = month_fixed + month_variable + month_category
        total_income += month_income
        total_expenses += month_expenses
        
        for member_id, amount in m.get("income", {}).items():
            member = next((mem for mem in config.get("members", []) if mem["id"] == member_id), None)
            if member:
                member_contributions[member["name"]] = member_contributions.get(member["name"], 0) + amount
        
        for exp in m.get("fixed_expenses", []):
            name = exp.get("name", "Otros")
            expense_by_category[name] = expense_by_category.get(name, 0) + exp.get("actual", 0)
        
        for exp in m.get("variable_expenses", []):
            name = exp.get("name", "Otros")
            expense_by_category[name] = expense_by_category.get(name, 0) + exp.get("actual", 0)
        
        monthly_summaries.append({
            "month": m.get("month"),
            "month_name": m.get("month_name"),
            "income": month_income,
            "expenses": month_expenses,
            "savings": month_income - month_expenses,
            "fixed_expenses": month_fixed,
            "variable_expenses": month_variable,
            "category_expenses": month_category,
            "bank_balances": m.get("bank_balances", {})
        })
    
    avg_monthly_savings = (total_income - total_expenses) / len(months) if months else 0
    remaining_months = 12 - len(months)
    projected_annual_savings = (total_income - total_expenses) + (avg_monthly_savings * remaining_months)
    
    return {
        "year": year,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_savings": total_income - total_expenses,
        "monthly_data": monthly_summaries,
        "expense_by_category": expense_by_category,
        "member_contributions": member_contributions,
        "savings_projection": {
            "current_savings": total_income - total_expenses,
            "avg_monthly_savings": avg_monthly_savings,
            "projected_annual_savings": projected_annual_savings,
            "months_tracked": len(months),
            "remaining_months": remaining_months
        }
    }

@api_router.get("/alerts")
async def get_alerts():
    months = await db.budget_months.find({}, {"_id": 0}).to_list(1000)
    config = await get_family_config()
    dismissed = await db.dismissed_alerts.find({}, {"_id": 0}).to_list(1000)
    dismissed_keys = set(d.get("alert_key") for d in dismissed)
    alerts = []
    
    for m in months:
        month_name = m.get("month_name", f"{m.get('year')}-{m.get('month')}")
        year = m.get("year")
        month_num = m.get("month")
        
        for exp in m.get("fixed_expenses", []):
            if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                alert_key = f"{year}-{month_num}-fixed-{exp.get('name')}"
                if alert_key not in dismissed_keys:
                    alerts.append({
                        "id": str(uuid.uuid4()),
                        "alert_key": alert_key,
                        "month": month_name,
                        "year": year,
                        "month_num": month_num,
                        "category": "Gastos Fijos",
                        "item_name": exp.get("name"),
                        "budget": exp.get("budget", 0),
                        "actual": exp.get("actual", 0),
                        "overage": exp.get("actual", 0) - exp.get("budget", 0),
                        "percentage_over": ((exp.get("actual", 0) - exp.get("budget", 0)) / exp.get("budget", 1)) * 100
                    })
        
        for exp in m.get("variable_expenses", []):
            if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                alert_key = f"{year}-{month_num}-variable-{exp.get('name')}"
                if alert_key not in dismissed_keys:
                    alerts.append({
                        "id": str(uuid.uuid4()),
                        "alert_key": alert_key,
                        "month": month_name,
                        "year": year,
                        "month_num": month_num,
                        "category": "Gastos Variables",
                        "item_name": exp.get("name"),
                        "budget": exp.get("budget", 0),
                        "actual": exp.get("actual", 0),
                        "overage": exp.get("actual", 0) - exp.get("budget", 0),
                        "percentage_over": ((exp.get("actual", 0) - exp.get("budget", 0)) / exp.get("budget", 1)) * 100
                    })
        
        for cat_id, expenses in m.get("category_expenses", {}).items():
            cat_name = next((c["name"] for c in config.get("categories", []) if c["id"] == cat_id), "Otros")
            for exp in expenses:
                if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                    alert_key = f"{year}-{month_num}-{cat_id}-{exp.get('name')}"
                    if alert_key not in dismissed_keys:
                        alerts.append({
                            "id": str(uuid.uuid4()),
                            "alert_key": alert_key,
                            "month": month_name,
                            "year": year,
                            "month_num": month_num,
                            "category": cat_name,
                            "item_name": exp.get("name"),
                            "budget": exp.get("budget", 0),
                            "actual": exp.get("actual", 0),
                            "overage": exp.get("actual", 0) - exp.get("budget", 0),
                            "percentage_over": ((exp.get("actual", 0) - exp.get("budget", 0)) / exp.get("budget", 1)) * 100
                        })
    
    return sorted(alerts, key=lambda x: x.get("overage", 0), reverse=True)

@api_router.post("/alerts/dismiss")
async def dismiss_alert(alert_key: str):
    await db.dismissed_alerts.insert_one({"alert_key": alert_key, "dismissed_at": datetime.now(timezone.utc).isoformat()})
    return {"message": "Alerta descartada"}

@api_router.delete("/alerts/clear-all")
async def clear_all_alerts():
    months = await db.budget_months.find({}, {"_id": 0}).to_list(1000)
    config = await get_family_config()
    dismissed_count = 0
    
    for m in months:
        year = m.get("year")
        month_num = m.get("month")
        
        for exp in m.get("fixed_expenses", []):
            if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                alert_key = f"{year}-{month_num}-fixed-{exp.get('name')}"
                existing = await db.dismissed_alerts.find_one({"alert_key": alert_key})
                if not existing:
                    await db.dismissed_alerts.insert_one({"alert_key": alert_key, "dismissed_at": datetime.now(timezone.utc).isoformat()})
                    dismissed_count += 1
        
        for exp in m.get("variable_expenses", []):
            if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                alert_key = f"{year}-{month_num}-variable-{exp.get('name')}"
                existing = await db.dismissed_alerts.find_one({"alert_key": alert_key})
                if not existing:
                    await db.dismissed_alerts.insert_one({"alert_key": alert_key, "dismissed_at": datetime.now(timezone.utc).isoformat()})
                    dismissed_count += 1
        
        for cat_id, expenses in m.get("category_expenses", {}).items():
            for exp in expenses:
                if exp.get("actual", 0) > exp.get("budget", 0) and exp.get("budget", 0) > 0:
                    alert_key = f"{year}-{month_num}-{cat_id}-{exp.get('name')}"
                    existing = await db.dismissed_alerts.find_one({"alert_key": alert_key})
                    if not existing:
                        await db.dismissed_alerts.insert_one({"alert_key": alert_key, "dismissed_at": datetime.now(timezone.utc).isoformat()})
                        dismissed_count += 1
    
    return {"message": f"{dismissed_count} alertas descartadas"}

@api_router.get("/template-excel")
async def get_template_excel():
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({'bold': True, 'bg_color': '#2563eb', 'font_color': 'white', 'border': 1, 'align': 'center'})
    subheader_format = workbook.add_format({'bold': True, 'bg_color': '#60a5fa', 'font_color': 'white', 'border': 1})
    money_format = workbook.add_format({'num_format': '$#,##0.00', 'border': 1})
    text_format = workbook.add_format({'border': 1})
    
    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    instructions = workbook.add_worksheet('INSTRUCCIONES')
    instructions.set_column('A:A', 80)
    instructions.write(0, 0, 'PLANTILLA DE PRESUPUESTO FAMILIAR', header_format)
    instructions.write(2, 0, '1. Cada hoja representa un mes del año')
    instructions.write(3, 0, '2. Llena los INGRESOS de cada miembro de la familia')
    instructions.write(4, 0, '3. En GASTOS FIJOS coloca gastos que no cambian')
    instructions.write(5, 0, '4. En GASTOS VARIABLES coloca gastos que varían')
    
    for i, month_name in enumerate(month_names, 1):
        ws = workbook.add_worksheet(month_name)
        ws.set_column('A:A', 30)
        ws.set_column('B:C', 15)
        row = 0
        ws.merge_range(row, 0, row, 2, f'PRESUPUESTO {month_name.upper()}', header_format)
        row += 2
        ws.write(row, 0, 'INGRESOS', subheader_format)
        ws.write(row, 1, 'MONTO', subheader_format)
        row += 1
        ws.write(row, 0, 'Miembro 1', text_format)
        ws.write(row, 1, 0, money_format)
        row += 1
        ws.write(row, 0, 'Miembro 2', text_format)
        ws.write(row, 1, 0, money_format)
    
    workbook.close()
    output.seek(0)
    
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           headers={"Content-Disposition": "attachment; filename=plantilla_presupuesto.xlsx"})

@api_router.get("/export-excel/{year}")
async def export_excel(year: int):
    months = await db.budget_months.find({"year": year}, {"_id": 0}).sort("month", 1).to_list(12)
    
    if not months:
        raise HTTPException(status_code=404, detail="No data for this year")
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({'bold': True, 'bg_color': '#2563eb', 'font_color': 'white', 'border': 1})
    money_format = workbook.add_format({'num_format': '$#,##0.00', 'border': 1})
    positive_format = workbook.add_format({'num_format': '$#,##0.00', 'bg_color': '#dcfce7', 'font_color': '#166534', 'border': 1})
    negative_format = workbook.add_format({'num_format': '$#,##0.00', 'bg_color': '#fee2e2', 'font_color': '#dc2626', 'border': 1})
    
    summary_sheet = workbook.add_worksheet('Resumen Anual')
    summary_headers = ['Mes', 'Ingresos', 'Gastos', 'Ahorro']
    
    for col, header in enumerate(summary_headers):
        summary_sheet.write(0, col, header, header_format)
    
    row = 1
    for m in months:
        income = sum(m.get("income", {}).values())
        fixed = sum(e.get("actual", 0) for e in m.get("fixed_expenses", []))
        variable = sum(e.get("actual", 0) for e in m.get("variable_expenses", []))
        category = sum(sum(e.get("actual", 0) for e in exps) for exps in m.get("category_expenses", {}).values())
        total_exp = fixed + variable + category
        savings = income - total_exp
        
        summary_sheet.write(row, 0, m.get("month_name", ""))
        summary_sheet.write(row, 1, income, money_format)
        summary_sheet.write(row, 2, total_exp, money_format)
        summary_sheet.write(row, 3, savings, positive_format if savings >= 0 else negative_format)
        row += 1
    
    workbook.close()
    output.seek(0)
    
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           headers={"Content-Disposition": f"attachment; filename=presupuesto_{year}.xlsx"})

@api_router.post("/create-year/{year}")
async def create_year(year: int):
    config = await get_family_config()
    members = config.get("members", [])
    categories = config.get("categories", [])
    
    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    created_count = 0
    
    for i in range(1, 13):
        existing = await db.budget_months.find_one({"year": year, "month": i})
        if existing:
            continue
        
        income = {member["id"]: 0 for member in members}
        category_expenses = {cat["id"]: [] for cat in categories}
        
        month_data = {
            "id": str(uuid.uuid4()),
            "year": year,
            "month": i,
            "month_name": month_names[i-1],
            "income": income,
            "fixed_expenses": [],
            "variable_expenses": [],
            "category_expenses": category_expenses,
            "savings": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.budget_months.insert_one(month_data)
        created_count += 1
    
    return {"message": f"Año {year} creado con {created_count} meses nuevos"}

@api_router.post("/seed-sample-data")
async def seed_sample_data():
    config = await get_family_config()
    members = config.get("members", [])
    categories = config.get("categories", [])
    
    if not members:
        members = [
            {"id": str(uuid.uuid4()), "name": "Nata", "percentage": 52.0},
            {"id": str(uuid.uuid4()), "name": "Jon", "percentage": 48.0}
        ]
    
    if not categories:
        categories = [
            {"id": str(uuid.uuid4()), "name": "Niños", "icon": "baby", "color": "#ec4899"},
            {"id": str(uuid.uuid4()), "name": "Casa", "icon": "home", "color": "#3b82f6"}
        ]
    
    await db.family_config.update_one({}, {"$set": {"members": members, "categories": categories, "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    
    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    sample_fixed = [
        {"name": "Hipoteca", "budget": 1500, "actual": 1500},
        {"name": "Servicios", "budget": 200, "actual": 0},
        {"name": "Internet", "budget": 60, "actual": 60},
        {"name": "Seguros", "budget": 150, "actual": 150},
    ]
    
    sample_variable = [
        {"name": "Restaurantes", "budget": 300, "actual": 0},
        {"name": "Supermercado", "budget": 600, "actual": 0},
        {"name": "Ropa", "budget": 150, "actual": 0},
    ]
    
    ninos_cat = next((c for c in categories if c["name"].lower() == "niños"), None)
    
    import random
    
    for i in range(1, 13):
        income = {}
        for member in members:
            base_salary = 4500 if member["percentage"] > 50 else 3500
            income[member["id"]] = base_salary + random.randint(-200, 200)
        
        category_expenses = {}
        if ninos_cat:
            category_expenses[ninos_cat["id"]] = [
                {"name": "Escuela", "budget": 500, "actual": 500 + random.randint(-50, 50)},
                {"name": "Actividades", "budget": 200, "actual": 200 + random.randint(-50, 100)},
            ]
        
        month_data = {
            "id": str(uuid.uuid4()),
            "year": 2024,
            "month": i,
            "month_name": month_names[i-1],
            "income": income,
            "fixed_expenses": [{**exp, "actual": exp["budget"] + random.randint(-20, 50)} for exp in sample_fixed],
            "variable_expenses": [{**exp, "actual": exp["budget"] + random.randint(-100, 150)} for exp in sample_variable],
            "category_expenses": category_expenses,
            "savings": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        existing = await db.budget_months.find_one({"year": 2024, "month": i})
        if existing:
            await db.budget_months.update_one({"year": 2024, "month": i}, {"$set": month_data})
        else:
            await db.budget_months.insert_one(month_data)
    
    return {"message": "Sample data seeded for 12 months of 2024"}

# Include the router
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
