import frappe

def add_insurance_repayments(bootinfo):
	bootinfo.insurance_repayments = frappe.db.get_single_value("FM Configuration", "insurance_repayments")
	bootinfo.fm_configuration = frappe.get_single("FM Configuration")
