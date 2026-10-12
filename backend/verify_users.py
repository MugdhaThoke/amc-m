#!/usr/bin/env python
"""Verify users were seeded to database."""
import sqlite3

conn = sqlite3.connect('data.db')
cursor = conn.cursor()

# Query users
cursor.execute('SELECT username, display_name, role, status FROM auth_users ORDER BY created_at DESC')
rows = cursor.fetchall()

print('\n' + '='*100)
print('✓ Users in database:')
print('='*100)
print(f"{'Username':<25} | {'Display Name':<20} | {'Role':<35} | {'Status':<10}")
print('-'*100)

for row in rows:
    print(f"{row[0]:<25} | {row[1]:<20} | {row[2]:<35} | {row[3]:<10}")

print('-'*100)
print(f'Total: {len(rows)} users\n')

# Check for Compliance Officer specifically
cursor.execute("SELECT * FROM auth_users WHERE username = 'compliance_officer'")
co = cursor.fetchone()

if co:
    print('✓ Compliance & Regulatory Officer user found:')
    print(f'  Username: {co[0]}')
    print(f'  Display Name: {co[1]}')
    print(f'  Role: {co[4]}')
    print(f'  Email: {co[3]}')
    print(f'  Status: {co[8]}')
    print(f'  Password: Compliance@2026')
    print()
else:
    print('✗ Compliance Officer user NOT found')

conn.close()
