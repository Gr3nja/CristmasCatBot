import discord
from discord import app_commands
from discord.ext import commands
import json
import random
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# クイズデータとユーザーポイントを保存
with open('quiz.json', 'r', encoding='utf-8') as f:
    quiz_data = json.load(f)

user_points = {}
active_quizzes = {}

def save_points():
    with open('points.json', 'w', encoding='utf-8') as f:
        json.dump(user_points, f, ensure_ascii=False, indent=2)

def load_points():
    global user_points
    try:
        with open('points.json', 'r', encoding='utf-8') as f:
            user_points = json.load(f)
    except FileNotFoundError:
        user_points = {}

@bot.event
async def on_ready():
    load_points()
    await bot.tree.sync()
    print(f'{bot.user} でログインしました')

async def end_quiz(user_id: str, interaction: discord.Interaction = None):
    if user_id not in active_quizzes:
        return
    
    quiz = active_quizzes[user_id]
    points = quiz['correct']
    if quiz['correct'] == 5:
        points = 10
    
    if user_id not in user_points:
        user_points[user_id] = 0
    user_points[user_id] += points
    save_points()
    
    # 全てのクイズメッセージを削除
    for msg in quiz['messages']:
        try:
            await msg.delete()
        except:
            pass
    
    embed = discord.Embed(
        title="クイズ終了",
        description=f"正解数: {quiz['correct']}/5\n獲得ポイント: {points}",
        color=discord.Color.gold()
    )
    
    if interaction:
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass
    
    del active_quizzes[user_id]

@bot.tree.command(name="quiz", description="クリスマスクイズに挑戦")
async def quiz(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id in active_quizzes:
        await interaction.response.send_message("既にクイズに挑戦中です", ephemeral=True)
        return
    
    questions = random.sample(quiz_data['questions'], 5)
    active_quizzes[user_id] = {
        'questions': questions,
        'current': 0,
        'correct': 0,
        'interaction': interaction,
        'messages': []
    }
    
    # 30秒後にクイズを強制終了
    asyncio.create_task(force_end_quiz(user_id, interaction))
    
    q = active_quizzes[user_id]['questions'][0]
    
    embed = discord.Embed(
        title=f"問題 1/5",
        description=q['question'],
        color=discord.Color.green()
    )
    
    view = QuizView(user_id, q['answer'])
    msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    # 最初のメッセージを記録（original_response）
    original_msg = await interaction.original_response()
    active_quizzes[user_id]['messages'].append(original_msg)

async def force_end_quiz(user_id: str, interaction: discord.Interaction):
    await asyncio.sleep(30)
    if user_id in active_quizzes:
        await end_quiz(user_id, interaction)

async def send_next_question(interaction: discord.Interaction, user_id: str):
    if user_id not in active_quizzes:
        return
    
    quiz = active_quizzes[user_id]
    q = quiz['questions'][quiz['current']]
    
    embed = discord.Embed(
        title=f"問題 {quiz['current'] + 1}/5",
        description=q['question'],
        color=discord.Color.green()
    )
    
    view = QuizView(user_id, q['answer'])
    msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
    
    # メッセージを記録
    active_quizzes[user_id]['messages'].append(msg)

class QuizView(discord.ui.View):
    def __init__(self, user_id: str, correct_answer: str):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.correct_answer = correct_answer
    
    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, "A")
    
    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, "B")
    
    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def button_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, "C")
    
    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def button_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.check_answer(interaction, "D")
    
    async def check_answer(self, interaction: discord.Interaction, answer: str):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("このクイズは他のユーザーのものです", ephemeral=True)
            return
        
        if self.user_id not in active_quizzes:
            await interaction.response.send_message("クイズは既に終了しています", ephemeral=True)
            return
        
        quiz = active_quizzes[self.user_id]
        is_correct = answer == self.correct_answer
        
        if is_correct:
            quiz['correct'] += 1
            result = "正解"
        else:
            result = f"不正解 (正解: {self.correct_answer})"
        
        await interaction.response.edit_message(view=None)
        result_msg = await interaction.followup.send(f"{result}", ephemeral=True, wait=True)
        
        # 結果メッセージも記録
        active_quizzes[self.user_id]['messages'].append(result_msg)
        
        quiz['current'] += 1
        
        if quiz['current'] < 5:
            await send_next_question(interaction, self.user_id)
        else:
            await end_quiz(self.user_id, interaction)

@bot.tree.command(name="ranking", description="ポイントランキングを表示")
async def ranking(interaction: discord.Interaction):
    if not user_points:
        await interaction.response.send_message("まだランキングデータがありません")
        return
    
    sorted_users = sorted(user_points.items(), key=lambda x: x[1], reverse=True)[:10]
    
    embed = discord.Embed(
        title="ポイントランキング TOP10",
        color=discord.Color.gold()
    )
    
    for i, (user_id, points) in enumerate(sorted_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            display_name = user.name
        except (discord.NotFound, discord.HTTPException):
            display_name = f"不明なユーザー ({user_id})"
        embed.add_field(
            name=f"{i}位",
            value=f"{display_name}: {points}ポイント",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="コマンドのヘルプを表示")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="コマンド一覧",
        description="クリスマスクイズBot",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="/quiz",
        value="クリスマスに関するクイズに挑戦します (5問)\n正解: 1ポイント/問、全問正解: 10ポイント",
        inline=False
    )
    embed.add_field(
        name="/ranking",
        value="ポイントランキングを表示します (上位10名)",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="このヘルプを表示します",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv('DISCORD_TOKEN'))