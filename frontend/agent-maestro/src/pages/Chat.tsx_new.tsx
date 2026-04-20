            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" && (
                <img src={msg.agent ? getAvatarUrl(msg.agent.avatar_color) : ""} alt={msg.agent.name} className="h-8 w-8 rounded-lg object-cover flex-shrink-0 mt-1" width={32} height={32} />
              )}