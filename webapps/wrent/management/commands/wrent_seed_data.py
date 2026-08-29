# webapps/wrent/management/commands/wrent_seed_data.py
from django.core.management.base import BaseCommand
from webapps.wrent.models import WrentStation, WrentVehicleCategory, WrentVehicle


class Command(BaseCommand):
    help = "播種 WRent 初始租賃站點、車型費率與車隊車輛資料"

    def handle(self, *args, **options):
        self.stdout.write("開始播種 WRent 初始資料...")

        # 1. 建立站點
        stations_def = [
            {"station_code": "TPE-MAIN", "name": "台北車站旗艦站", "address": "台北市中正區北平西路3號", "capacity": 20, "contact_phone": "02-2381-0001"},
            {"station_code": "NTP-BQC", "name": "板橋車站轉運站", "address": "新北市板橋區縣民大道二段7號", "capacity": 15, "contact_phone": "02-8968-0002"},
            {"station_code": "TXG-CITY", "name": "台中市政站", "address": "台中市西屯區台灣大道三段99號", "capacity": 12, "contact_phone": "04-2228-0003"},
            {"station_code": "KHH-ZUY", "name": "高鐵左營站", "address": "高雄市左營區高鐵路105號", "capacity": 15, "contact_phone": "07-862-0004"},
        ]

        station_objs = {}
        for s in stations_def:
            obj, _ = WrentStation.objects.update_or_create(
                station_code=s["station_code"],
                defaults=s,
            )
            station_objs[s["station_code"]] = obj

        # 2. 建立車型與費率
        categories_def = [
            {
                "category_code": "ECONOMY",
                "name": "經濟型小客車 (Yaris / Vios)",
                "hourly_rate": 120.00,
                "daily_cap_rate": 1200.00,
                "mileage_rate": 3.20,
                "overdue_hourly_rate": 180.00,
                "deposit_amount": 1000.00,
                "description": "省油都會五人座，適合市區通勤與日常短途代步。",
            },
            {
                "category_code": "SUV",
                "name": "多功能休旅車 (RAV4 / Kuga)",
                "hourly_rate": 180.00,
                "daily_cap_rate": 1800.00,
                "mileage_rate": 3.80,
                "overdue_hourly_rate": 250.00,
                "deposit_amount": 1500.00,
                "description": "大空間視野佳，適合家庭出遊或長途戶外旅程。",
            },
            {
                "category_code": "VAN",
                "name": "豪華商務廂型車 (Sienna / Alphard)",
                "hourly_rate": 250.00,
                "daily_cap_rate": 2500.00,
                "mileage_rate": 4.50,
                "overdue_hourly_rate": 350.00,
                "deposit_amount": 3000.00,
                "description": "七至八人座尊榮座艙，適合團體商務接送與長途旅行。",
            },
        ]

        category_objs = {}
        for c in categories_def:
            obj, _ = WrentVehicleCategory.objects.update_or_create(
                category_code=c["category_code"],
                defaults=c,
            )
            category_objs[c["category_code"]] = obj

        # 3. 建立車輛實體
        vehicles_def = [
            {"plate_number": "RDG-1688", "category": "ECONOMY", "station": "TPE-MAIN", "model_name": "Toyota Yaris Cross", "current_mileage": 12500.0, "fuel_or_battery_level": 95},
            {"plate_number": "RDG-2358", "category": "ECONOMY", "station": "NTP-BQC", "model_name": "Toyota Vios 1.5", "current_mileage": 28400.0, "fuel_or_battery_level": 100},
            {"plate_number": "SUV-9999", "category": "SUV", "station": "TPE-MAIN", "model_name": "Toyota RAV4 Hybrid", "current_mileage": 8200.0, "fuel_or_battery_level": 88},
            {"plate_number": "SUV-7777", "category": "SUV", "station": "TXG-CITY", "model_name": "Ford Kuga 250 AWD", "current_mileage": 15600.0, "fuel_or_battery_level": 100},
            {"plate_number": "VAN-5555", "category": "VAN", "station": "KHH-ZUY", "model_name": "Toyota Sienna 2.5", "current_mileage": 31200.0, "fuel_or_battery_level": 90},
        ]

        for v in vehicles_def:
            WrentVehicle.objects.update_or_create(
                plate_number=v["plate_number"],
                defaults={
                    "category": category_objs[v["category"]],
                    "current_station": station_objs[v["station"]],
                    "model_name": v["model_name"],
                    "current_mileage": v["current_mileage"],
                    "fuel_or_battery_level": v["fuel_or_battery_level"],
                    "status": "AVAILABLE",
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("WRent 初始資料播種完成！包含 4 處站點、3 款車型費率及 5 輛車隊實體。"))
