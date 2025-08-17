"""
Universal Discord AI - Character Manager
人格設定の管理を行うモジュール
"""

import os
import logging
from typing import Dict, Optional
import aiofiles
import markdown


class CharacterManager:
    """人格設定の管理クラス"""
    
    def __init__(self, characters_dir: str = "characters"):
        self.characters_dir = characters_dir
        self.logger = logging.getLogger(__name__)
        self.characters: Dict[str, Dict] = {}
        
    async def load_all_characters(self) -> Dict[str, Dict]:
        """全ての人格設定を読み込み"""
        self.characters.clear()
        
        if not os.path.exists(self.characters_dir):
            self.logger.error(f"人格設定ディレクトリが見つかりません: {self.characters_dir}")
            return self.characters
            
        try:
            # ディレクトリ内の.mdファイルを取得
            character_files = [
                f for f in os.listdir(self.characters_dir) 
                if f.endswith('.md')
            ]
            
            self.logger.info(f"人格設定ファイルを発見: {character_files}")
            
            # 各ファイルを読み込み
            for file_name in character_files:
                character_name = file_name.replace('.md', '')
                character_data = await self.load_character(character_name)
                
                if character_data:
                    self.characters[character_name] = character_data
                    self.logger.info(f"人格設定を読み込み: {character_name}")
                else:
                    self.logger.warning(f"人格設定の読み込みに失敗: {character_name}")
                    
        except Exception as e:
            self.logger.error(f"人格設定の読み込み中にエラー: {e}")
            
        return self.characters
        
    async def load_character(self, character_name: str) -> Optional[Dict]:
        """指定された人格設定を読み込み"""
        file_path = os.path.join(self.characters_dir, f"{character_name}.md")
        
        if not os.path.exists(file_path):
            self.logger.error(f"人格設定ファイルが見つかりません: {file_path}")
            return None
            
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
                content = await file.read()
                
            # Markdownを解析して人格データを構築
            character_data = self.parse_character_markdown(content)
            character_data['file_path'] = file_path
            character_data['name'] = character_name
            
            return character_data
            
        except Exception as e:
            self.logger.error(f"人格設定ファイルの読み込みエラー ({file_path}): {e}")
            return None
            
    def parse_character_markdown(self, content: str) -> Dict:
        """Markdownの人格設定を解析"""
        character_data = {
            'content': content,
            'sections': {},
            'personality': '',
            'speaking_style': '',
            'specialties': '',
            'examples': '',
            'avoid': '',
            'features': ''
        }
        
        try:
            # Markdownをセクションごとに分割
            sections = content.split('\n## ')
            
            for section in sections:
                if not section.strip():
                    continue
                    
                lines = section.strip().split('\n')
                if len(lines) < 2:
                    continue
                    
                # セクションタイトルを取得（#を除去）
                title = lines[0].replace('# ', '').replace('## ', '').strip()
                section_content = '\n'.join(lines[1:]).strip()
                
                character_data['sections'][title] = section_content
                
                # 主要なセクションをマッピング
                title_lower = title.lower()
                if '基本性格' in title or '性格' in title:
                    character_data['personality'] = section_content
                elif '話し方' in title or '口調' in title:
                    character_data['speaking_style'] = section_content
                elif '専門分野' in title or '得意' in title:
                    character_data['specialties'] = section_content
                elif '返答例' in title or '例' in title:
                    character_data['examples'] = section_content
                elif '避ける' in title or '禁止' in title:
                    character_data['avoid'] = section_content
                elif '特徴' in title or 'その他' in title:
                    character_data['features'] = section_content
                    
        except Exception as e:
            self.logger.error(f"Markdown解析エラー: {e}")
            
        return character_data
        
    def get_character(self, character_name: str) -> Optional[Dict]:
        """指定された人格設定を取得"""
        return self.characters.get(character_name)
        
    def list_characters(self) -> list:
        """利用可能な人格設定の一覧を取得"""
        return list(self.characters.keys())
        
    def get_character_summary(self, character_name: str) -> Optional[str]:
        """人格設定の要約を取得"""
        character = self.get_character(character_name)
        if not character:
            return None
            
        summary_parts = []
        
        if character.get('personality'):
            summary_parts.append(f"性格: {character['personality'][:100]}...")
            
        if character.get('speaking_style'):
            summary_parts.append(f"話し方: {character['speaking_style'][:100]}...")
            
        if character.get('specialties'):
            summary_parts.append(f"専門分野: {character['specialties'][:100]}...")
            
        return '\n'.join(summary_parts) if summary_parts else "要約情報なし"
        
    async def reload_character(self, character_name: str) -> bool:
        """指定された人格設定を再読み込み"""
        character_data = await self.load_character(character_name)
        
        if character_data:
            self.characters[character_name] = character_data
            self.logger.info(f"人格設定を再読み込み: {character_name}")
            return True
        else:
            self.logger.error(f"人格設定の再読み込みに失敗: {character_name}")
            return False
            
    async def reload_all_characters(self) -> int:
        """全ての人格設定を再読み込み"""
        old_count = len(self.characters)
        await self.load_all_characters()
        new_count = len(self.characters)
        
        self.logger.info(f"人格設定を再読み込み: {old_count} -> {new_count}")
        return new_count
        
    def validate_character(self, character_data: Dict) -> bool:
        """人格設定の妥当性をチェック"""
        required_fields = ['content', 'name']
        
        for field in required_fields:
            if field not in character_data or not character_data[field]:
                self.logger.warning(f"必須フィールドが不足: {field}")
                return False
                
        # コンテンツの長さチェック
        if len(character_data['content']) < 50:
            self.logger.warning("人格設定のコンテンツが短すぎます")
            return False
            
        return True
        
    def get_character_for_context(self, character_name: str) -> str:
        """AIコンテキスト用の人格設定文字列を生成"""
        character = self.get_character(character_name)
        if not character:
            return "デフォルトの人格設定が見つかりません。"
            
        context_parts = []
        
        # 基本情報
        context_parts.append(f"あなたは「{character_name}」という人格です。")
        
        # 各セクションを追加
        if character.get('personality'):
            context_parts.append(f"\n【基本性格】\n{character['personality']}")
            
        if character.get('speaking_style'):
            context_parts.append(f"\n【話し方】\n{character['speaking_style']}")
            
        if character.get('specialties'):
            context_parts.append(f"\n【専門分野・得意なこと】\n{character['specialties']}")
            
        if character.get('examples'):
            context_parts.append(f"\n【返答例】\n{character['examples']}")
            
        if character.get('avoid'):
            context_parts.append(f"\n【避けるべき表現】\n{character['avoid']}")
            
        if character.get('features'):
            context_parts.append(f"\n【その他の特徴】\n{character['features']}")
            
        context_parts.append("\n上記の人格設定に従って、自然で一貫性のある返答をしてください。")
        
        return '\n'.join(context_parts)
