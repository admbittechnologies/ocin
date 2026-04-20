import avatar01 from "@/assets/avatars/avatar-01.png";
import avatar02 from "@/assets/avatars/avatar-02.png";
import avatar03 from "@/assets/avatars/avatar-03.png";
import avatar04 from "@/assets/avatars/avatar-04.png";
import avatar05 from "@/assets/avatars/avatar-05.png";
import avatar06 from "@/assets/avatars/avatar-06.png";
import avatar07 from "@/assets/avatars/avatar-07.png";
import avatar08 from "@/assets/avatars/avatar-08.png";
import avatar09 from "@/assets/avatars/avatar-09.png";
import avatar10 from "@/assets/avatars/avatar-10.png";
import avatar11 from "@/assets/avatars/avatar-11.png";
import avatar12 from "@/assets/avatars/avatar-12.png";
import avatar13 from "@/assets/avatars/avatar-13.png";
import avatar14 from "@/assets/avatars/avatar-14.png";
import avatar15 from "@/assets/avatars/avatar-15.png";
import avatar16 from "@/assets/avatars/avatar-16.png";
import avatar17 from "@/assets/avatars/avatar-17.png";
import avatar18 from "@/assets/avatars/avatar-18.png";
import avatar19 from "@/assets/avatars/avatar-19.png";
import avatar20 from "@/assets/avatars/avatar-20.png";
import avatar21 from "@/assets/avatars/avatar-21.png";
import avatar22 from "@/assets/avatars/avatar-22.png";
import avatar23 from "@/assets/avatars/avatar-23.png";
import avatar24 from "@/assets/avatars/avatar-24.png";
import avatar25 from "@/assets/avatars/avatar-25.png";
import avatar26 from "@/assets/avatars/avatar-26.png";
import avatar27 from "@/assets/avatars/avatar-27.png";
import avatar28 from "@/assets/avatars/avatar-28.png";
import avatar29 from "@/assets/avatars/avatar-29.png";
import avatar30 from "@/assets/avatars/avatar-30.png";

import ocinAvatar from "@/assets/avatars/ocin-avatar.png";

export const AVATARS: string[] = [
  avatar01,
  avatar02,
  avatar03,
  avatar04,
  avatar05,
  avatar06,
  avatar07,
  avatar08,
  avatar09,
  avatar10,
  avatar11,
  avatar12,
  avatar13,
  avatar14,
  avatar15,
  avatar16,
  avatar17,
  avatar18,
  avatar19,
  avatar20,
  avatar21,
  avatar22,
  avatar23,
  avatar24,
  avatar25,
  avatar26,
  avatar27,
  avatar28,
  avatar29,
  avatar30,
];

// Map avatar names to imported image URLs
export const AVATAR_MAP: Record<string, string> = {
  "avatar-01": avatar01,
  "avatar-02": avatar02,
  "avatar-03": avatar03,
  "avatar-04": avatar04,
  "avatar-05": avatar05,
  "avatar-06": avatar06,
  "avatar-07": avatar07,
  "avatar-08": avatar08,
  "avatar-09": avatar09,
  "avatar-10": avatar10,
  "avatar-11": avatar11,
  "avatar-12": avatar12,
  "avatar-13": avatar13,
  "avatar-14": avatar14,
  "avatar-15": avatar15,
  "avatar-16": avatar16,
  "avatar-17": avatar17,
  "avatar-18": avatar18,
  "avatar-19": avatar19,
  "avatar-20": avatar20,
  "avatar-21": avatar21,
  "avatar-22": avatar22,
  "avatar-23": avatar23,
  "avatar-24": avatar24,
  "avatar-25": avatar25,
  "avatar-26": avatar26,
  "avatar-27": avatar27,
  "avatar-28": avatar28,
  "avatar-29": avatar29,
  "avatar-30": avatar30,
};

// Helper function to get avatar source URL from avatar name
export function getAvatarSrc(avatar: string | undefined): string {
  if (!avatar) return AVATARS[0];
  return AVATAR_MAP[avatar] || AVATARS[0];
}
